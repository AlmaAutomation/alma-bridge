from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder

from alma_bridge.compatibility.strategies import STRATEGIES, classify_binary
from alma_bridge.config import settings
from alma_bridge.storage.outcomes import _connect

CANONICAL_STRATEGY_IDS = {strategy.id for strategy in STRATEGIES}

CATEGORICAL_FIELDS = (
    "strategy_id",
    "runtime",
    "binary_format",
    "gpu_vendor",
    "storage_type",
    "error_signature",
)

NUMERIC_FIELDS = (
    "wine_cap",
    "docker_cap",
    "multiarch_cap",
    "proton_cap",
    "ram_gb",
    "legacy_count",
    "has_remediation",
)


def normalize_strategy_id(strategy_id: str, runtime: str, file_path: str) -> str:
    if strategy_id in CANONICAL_STRATEGY_IDS:
        return strategy_id

    if strategy_id.startswith("sysdet_"):
        runtime = strategy_id.removeprefix("sysdet_") or runtime

    path_lower = file_path.lower()
    runtime_lower = (runtime or "").lower()

    if runtime_lower == "wine" or strategy_id == "wine_host":
        return "wine_host"
    if runtime_lower == "proton":
        return "proton_host"
    if runtime_lower == "native":
        return "native_host"
    if ".appimage" in path_lower:
        return "native_host"
    if path_lower.endswith((".exe", ".msi")):
        return "wine_host"
    if "qemu" in runtime_lower:
        return "qemu_user"
    if "docker" in runtime_lower or "container" in strategy_id:
        return "container_compat"
    if "hello32" in path_lower or "i386" in path_lower or "32" in path_lower:
        return "native_multiarch"
    return "native_host"


def infer_binary_format(file_path: str, host_arch: str = "x86_64") -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".appimage":
        return "appimage"
    if suffix in {".exe", ".msi"}:
        return "pe"
    if suffix in {".sh", ".py"}:
        return "script"
    if path.exists():
        return classify_binary(file_path, host_arch)
    name = path.name.lower()
    if "appimage" in name:
        return "appimage"
    if name.endswith((".exe", ".msi")):
        return "pe"
    return "unknown"


def build_feature_row(record: Dict[str, Any]) -> Dict[str, Any]:
    hardware = record.get("hardware_profile") or {}
    if isinstance(hardware, str):
        hardware = json.loads(hardware)

    capabilities = hardware.get("capabilities", {})
    gpu = hardware.get("gpu", {})
    asod = hardware.get("asod", {})
    file_path = record.get("file_path") or ""
    host_arch = hardware.get("architecture", "x86_64")

    strategy_id = normalize_strategy_id(
        record.get("strategy_id") or "unknown",
        record.get("runtime") or "unknown",
        file_path,
    )

    return {
        "strategy_id": strategy_id,
        "runtime": record.get("runtime") or "unknown",
        "binary_format": infer_binary_format(file_path, host_arch),
        "gpu_vendor": gpu.get("vendor") or asod.get("gpu") or "unknown",
        "storage_type": hardware.get("storage_type") or asod.get("storage") or "unknown",
        "error_signature": record.get("error_signature") or "none",
        "wine_cap": int(bool(capabilities.get("wine"))),
        "docker_cap": int(bool(capabilities.get("docker"))),
        "multiarch_cap": int(bool(capabilities.get("multiarch"))),
        "proton_cap": int(bool(capabilities.get("proton"))),
        "ram_gb": float(hardware.get("ram_gb") or asod.get("ram_gb") or 0.0),
        "legacy_count": len(hardware.get("legacy_indicators") or []),
        "has_remediation": int(bool(record.get("remediation_id"))),
    }


def load_training_records() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.strategy_id,
                a.runtime,
                a.remediation_id,
                a.error_signature,
                a.success,
                s.file_path,
                s.hardware_profile
            FROM bridge_attempts a
            JOIN bridge_sessions s ON s.session_id = a.session_id
            ORDER BY a.id ASC
            """
        ).fetchall()

    records = []
    for row in rows:
        item = dict(row)
        item["hardware_profile"] = json.loads(item.get("hardware_profile") or "{}")
        item["success"] = bool(item.get("success"))
        records.append(item)
    return records


def maybe_auto_retrain(
    *,
    min_records: int = 8,
    min_new_records: int = 5,
) -> Dict[str, Any] | None:
    """Retrain when enough new outcomes have accumulated since the last train."""
    records = load_training_records()
    if len(records) < min_records:
        return None

    metadata = load_ranker_metadata() or {}
    last_count = int(metadata.get("records") or 0)
    if metadata and len(records) - last_count < min_new_records:
        return None

    return train_strategy_ranker()


def train_strategy_ranker(
    *,
    model_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Dict[str, Any]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_path or settings.ranker_model_path
    meta_file = metadata_path or settings.ranker_metadata_path
    model_file.parent.mkdir(parents=True, exist_ok=True)

    records = load_training_records()
    if len(records) < 8:
        return {
            "trained": False,
            "reason": f"Not enough training records ({len(records)}). Need at least 8.",
            "records": len(records),
        }

    feature_rows = [build_feature_row(record) for record in records]
    labels = np.array([int(record["success"]) for record in records], dtype=np.int64)

    cat_matrix = [[row[field] for field in CATEGORICAL_FIELDS] for row in feature_rows]
    num_matrix = np.array(
        [[row[field] for field in NUMERIC_FIELDS] for row in feature_rows],
        dtype=np.float64,
    )

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoded = encoder.fit_transform(cat_matrix)

    positives = int(labels.sum())
    if positives == 0 or positives == len(labels):
        return {
            "trained": False,
            "reason": "Need both successes and failures in the dataset to train a ranker.",
            "records": len(records),
            "successes": positives,
            "failures": len(labels) - positives,
        }

    X = np.hstack([encoded, num_matrix])

    stratify = labels if min(positives, len(labels) - positives) >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        labels,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify,
    )

    model = HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.1,
        max_iter=200,
        random_state=random_state,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test) if len(X_test) else np.array([], dtype=np.int64)
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)) if len(y_test) else None,
        "precision": float(precision_score(y_test, y_pred, zero_division=0))
        if len(y_test)
        else None,
        "recall": float(recall_score(y_test, y_pred, zero_division=0)) if len(y_test) else None,
        "f1": float(f1_score(y_test, y_pred, zero_division=0)) if len(y_test) else None,
    }

    strategy_rates = _strategy_success_rates(feature_rows, labels)

    artifact = {
        "model": model,
        "encoder": encoder,
        "categorical_fields": CATEGORICAL_FIELDS,
        "numeric_fields": NUMERIC_FIELDS,
    }
    joblib.dump(artifact, model_file)

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "records": len(records),
        "successes": positives,
        "failures": len(labels) - positives,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "metrics": metrics,
        "strategy_success_rates": strategy_rates,
        "model_path": str(model_file),
    }
    meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {"trained": True, **metadata}


def load_ranker_artifact() -> Optional[Dict[str, Any]]:
    model_file = settings.ranker_model_path
    if not model_file.exists():
        return None
    try:
        return joblib.load(model_file)
    except Exception:
        return None


def load_ranker_metadata() -> Optional[Dict[str, Any]]:
    meta_file = settings.ranker_metadata_path
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def predict_success_probability(
    artifact: Dict[str, Any],
    *,
    strategy_id: str,
    runtime: str,
    file_path: str,
    hardware_profile: Dict[str, Any],
    error_signature: Optional[str] = None,
) -> float:
    row = build_feature_row(
        {
            "strategy_id": strategy_id,
            "runtime": runtime,
            "file_path": file_path,
            "hardware_profile": hardware_profile,
            "error_signature": error_signature or "none",
            "remediation_id": None,
        }
    )

    cat_matrix = [[row[field] for field in artifact["categorical_fields"]]]
    num_matrix = np.array(
        [[row[field] for field in artifact["numeric_fields"]]],
        dtype=np.float64,
    )
    encoded = artifact["encoder"].transform(cat_matrix)
    features = np.hstack([encoded, num_matrix])

    model = artifact["model"]
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(features)[0]
        classes = list(model.classes_)
        if 1 in classes:
            return float(proba[classes.index(1)])
        return float(max(proba))
    prediction = model.predict(features)[0]
    return float(prediction)


def _strategy_success_rates(
    feature_rows: List[Dict[str, Any]],
    labels: np.ndarray,
) -> Dict[str, Dict[str, float]]:
    totals: Dict[str, List[int]] = {}
    for row, label in zip(feature_rows, labels):
        strategy = row["strategy_id"]
        totals.setdefault(strategy, []).append(int(label))

    rates: Dict[str, Dict[str, float]] = {}
    for strategy, outcomes in totals.items():
        successes = sum(outcomes)
        attempts = len(outcomes)
        rates[strategy] = {
            "attempts": attempts,
            "successes": successes,
            "success_rate": round(successes / attempts, 4) if attempts else 0.0,
        }
    return rates

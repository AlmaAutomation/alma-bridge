from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALMA_ROOT = PROJECT_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALMA_BRIDGE_",
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bridge_build: str = "2026.06.08-launcher-decoy"
    data_dir: Path = Path("data")
    db_path: Path = Path("data/outcomes.db")
    max_attempts: int = 8
    execution_timeout_sec: int = 120
    # GUI launchers (Electron) detach once the process survives bootstrap —
    # killing them at execution_timeout_sec caused false "Execution timed out" failures.
    launcher_detach_after_sec: int = 45
    launcher_bootstrap_timeout_sec: int = 180
    wine_gui_startup_timeout_sec: float = 15.0
    wine_gui_survival_sec: float = 3.0
    wine_gui_bootstrap_timeout_sec: int = 90
    sandbox_image: str = "alma-bridge-sandbox:latest"
    sandbox_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 9010
    sysdet_db_path: Path = ALMA_ROOT / "almasysdet" / "data" / "alma.db"
    resolve_audit_dir: Path = ALMA_ROOT / "alma_resolve" / "runtime_data" / "audit"
    ranker_model_path: Path = Path("data/models/strategy_ranker.joblib")
    ranker_metadata_path: Path = Path("data/models/strategy_ranker.json")
    auto_retrain_after_run: bool = True
    auto_retrain_min_records: int = 8
    auto_retrain_min_new_records: int = 5

    # Legacy compliance (TLS + drivers/shims)
    compliance_ca_file: str | None = None
    compliance_tls_timeout: float = 6.0
    compliance_sys_root: str = "/sys"
    compliance_driver_catalog_db: Path = (
        ALMA_ROOT / "automatic driver detection" / "driver_compatibility.db"
    )
    compliance_bridge_listen_host: str = "127.0.0.1"
    # Performance: 0 workers = auto-tune from CPU (capped). cache_ttl seconds
    # memoizes probes so repeated/overlapping scans are near-instant.
    compliance_max_workers: int = 0
    compliance_cache_ttl: float = 60.0

    # Automation platform — comma-separated webhook URLs for lifecycle events
    automation_webhook_urls: str = ""

    # Optional API key for mutating endpoints (empty = open, for local dev)
    api_key: str | None = None

    # Commercial: automation audit retention (days); 0 = keep forever
    compliance_data_retention_days: int = 365

    # --- AI Operator (autonomous observe → decide → apply → verify) ---
    # Master switch for the background loop. Off by default.
    operator_enabled: bool = False
    # observe | recommend | assisted | autonomous
    operator_autonomy: str = "recommend"
    # The operator only applies host changes when this is also true.
    operator_allow_mutations: bool = False
    # Seconds between autonomous cycles when the loop is running.
    operator_interval_sec: int = 900
    # Highest risk class the operator may auto-apply: low | medium | high
    operator_max_risk: str = "low"
    # Minimum blended confidence for an action to be auto-eligible.
    operator_min_confidence: float = 0.7
    # When autonomous + mutations: apply every mitigation/step within max_risk
    # (ignore min_confidence). Full troubleshoot-and-fix mode.
    operator_apply_all: bool = True
    # Max ranked routes (Bridge + pathways + synthesis) per operator cycle.
    operator_max_route_attempts: int = 12
    operator_bridge_max_attempts: int = 12
    operator_try_all_pathways: bool = True

    # After Bridge exhausts its retry loop, automatically run ranked routes
    # (winetricks, autopilot pathways, heal-then-bridge) until the program works.
    bridge_auto_remediate: bool = True
    session_lease_sec: int = 300
    prefix_lock_timeout_sec: int = 120
    session_timeout_sec: int = 3600
    per_remediation_retry_limit: int = 2

    # Auto-compatibility escalation budget (session-scoped)
    auto_compat_max_execution_attempts: int = 64
    auto_compat_max_routes: int = 12
    auto_compat_max_bridge_retries: int = 8
    auto_compat_max_remediations: int = 32
    auto_compat_max_identical_tuple: int = 4
    auto_compat_wall_clock_sec: int = 3600

    # Validation campaign guards (operational only; not global production policy)
    validation_campaign_mode: bool = False
    validation_campaign_id: str | None = None
    validation_campaign_disposable_root: str | None = None
    validation_campaign_primary_prefix: str | None = None
    validation_campaign_source_snapshot: str | None = None

    # Compatibility profiles (Phase 1 infrastructure; creation gated separately)
    compatibility_profiles_enabled: bool = False
    compatibility_profile_creation_enabled: bool = False
    compatibility_profile_shadow_mode: bool = False
    compatibility_profile_reuse_enabled: bool = False

    # Advisor optional LLM rendering (Phase 2 — disabled by default)
    advisor_llm_enabled: bool = Field(default=False, validation_alias="ALMA_ADVISOR_LLM_ENABLED")
    advisor_llm_provider: str = Field(default="", validation_alias="ALMA_ADVISOR_LLM_PROVIDER")
    advisor_llm_model: str = Field(default="", validation_alias="ALMA_ADVISOR_LLM_MODEL")
    advisor_llm_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="ALMA_ADVISOR_LLM_TIMEOUT_SECONDS",
    )


settings = Settings()

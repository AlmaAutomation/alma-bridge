from __future__ import annotations

from alma_bridge.compatibility.strategies import STRATEGIES
from alma_bridge.learning.ranker import (
    _format_boost,
    rank_strategies,
    rerank_plans,
    score_strategies,
)


def test_pe_prefers_wine_over_container():
    assert _format_boost(_by_id("wine_host"), "pe") > _format_boost(_by_id("container_compat"), "pe")


def test_appimage_prefers_native():
    assert _format_boost(_by_id("native_host"), "appimage") > _format_boost(
        _by_id("container_compat"), "appimage"
    )


def test_installer_prefers_wine_over_proton():
    assert _format_boost(_by_id("wine_host"), "pe", file_path="/tmp/foo-setup-1.0.exe") > _format_boost(
        _by_id("proton_host"), "pe", file_path="/tmp/foo-setup-1.0.exe"
    )


def test_rank_pe_puts_wine_before_container():
    ranked = rank_strategies(
        STRATEGIES,
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True, "docker": True}},
    )
    ids = [strategy.id for strategy in ranked if strategy.id in {"wine_host", "container_compat"}]
    assert ids.index("wine_host") < ids.index("container_compat")


def test_score_strategies_includes_rank_metadata():
    scored = score_strategies(
        STRATEGIES[:3],
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True}},
    )
    assert len(scored) == 3
    assert scored[0]["rank_position"] == 1
    assert scored[0]["rank_source"] in {"ml", "historical", "static"}
    assert "rank_score" in scored[0]


def test_score_strategies_uses_signature_historical_rates(monkeypatch, tmp_path):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.learning.ranker.load_ranker_artifact", lambda: None)

    from alma_bridge.storage.outcomes import import_attempt, import_session, init_outcome_store

    init_outcome_store()
    session_id = import_session(
        file_path="/tmp/game.exe",
        file_hash="abc",
        started_at="2026-06-08T00:00:00",
        finished_at="2026-06-08T00:00:05",
        success=False,
        hardware_profile={"architecture": "x86_64"},
        summary="test",
        source="test",
    )
    for strategy_id, success in (("wine_host", True), ("proton_host", False)):
        import_attempt(
            session_id=session_id,
            attempt_number=1,
            strategy_id=strategy_id,
            remediation_id=None,
            runtime="wine" if strategy_id == "wine_host" else "proton",
            command=["wine", "/tmp/game.exe"],
            env={},
            mode="host",
            success=success,
            exit_code=0 if success else 1,
            error_signature="missing_dll",
            detected_error="missing dll",
            stdout="",
            stderr="",
            duration_ms=100,
            created_at="2026-06-08T00:00:01",
        )

    scored = score_strategies(
        [_by_id("proton_host"), _by_id("wine_host")],
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True}},
        error_signature="missing_dll",
    )
    assert scored[0]["strategy"].id == "wine_host"
    assert scored[0]["rank_source"] == "historical"


def test_score_strategies_uses_error_signature(monkeypatch):
    artifact = object()

    def fake_predict(_artifact, *, strategy_id, error_signature=None, **kwargs):
        if error_signature == "missing_dll" and strategy_id == "wine_host":
            return 0.9
        if strategy_id == "proton_host":
            return 0.2
        return 0.5

    monkeypatch.setattr("alma_bridge.learning.ranker.load_ranker_artifact", lambda: artifact)
    monkeypatch.setattr(
        "alma_bridge.learning.ranker.predict_success_probability",
        fake_predict,
    )

    scored = score_strategies(
        [_by_id("proton_host"), _by_id("wine_host")],
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True}},
        error_signature="missing_dll",
    )
    assert scored[0]["strategy"].id == "wine_host"


def test_rerank_plans_reorders_queue(monkeypatch):
    artifact = object()

    def fake_predict(_artifact, *, strategy_id, error_signature=None, **kwargs):
        if error_signature == "permission_denied" and strategy_id == "proton_host":
            return 0.95
        return 0.1

    monkeypatch.setattr("alma_bridge.learning.ranker.load_ranker_artifact", lambda: artifact)
    monkeypatch.setattr(
        "alma_bridge.learning.ranker.predict_success_probability",
        fake_predict,
    )

    plans = [
        {"strategy_id": "wine_host", "runtime": "wine", "mode": "host", "command": ["wine", "a.exe"], "env": {}},
        {"strategy_id": "proton_host", "runtime": "proton", "mode": "host", "command": ["proton", "run", "a.exe"], "env": {}},
    ]
    reranked = rerank_plans(
        plans,
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True}},
        error_signature="permission_denied",
    )
    assert reranked[0]["strategy_id"] == "proton_host"
    assert reranked[0]["reranked_for_signature"] == "permission_denied"


def test_preferred_strategy_is_tried_first():
    ranked = rank_strategies(
        STRATEGIES,
        file_path="/tmp/game.exe",
        hardware_profile={"architecture": "x86_64", "capabilities": {"wine": True, "docker": True}},
        preferred_strategy_id="container_compat",
    )
    assert ranked[0].id == "container_compat"


def _by_id(strategy_id: str):
    return next(strategy for strategy in STRATEGIES if strategy.id == strategy_id)

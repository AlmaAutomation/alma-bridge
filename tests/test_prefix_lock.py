"""Prefix flock lock tests."""

from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

import pytest

from alma_bridge.session.prefix_lock import prefix_lock, prefix_lock_path


def _hold_lock(prefix: str, session_id: str, hold_sec: float, result_path: str) -> None:
    from alma_bridge.session.prefix_lock import prefix_lock as pl

    try:
        with pl(prefix, session_id=session_id, timeout_sec=0.2):
            Path(result_path).write_text("held", encoding="utf-8")
            time.sleep(hold_sec)
    except Exception:
        Path(result_path).write_text("timeout", encoding="utf-8")


def test_persistent_lock_file_allows_reacquisition(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    prefix = str(tmp_path / "wine-prefix")
    Path(prefix).mkdir()
    with prefix_lock(prefix, session_id="s1", timeout_sec=2):
        lock_path = prefix_lock_path(prefix)
        assert lock_path.is_file()
    with prefix_lock(prefix, session_id="s2", timeout_sec=2):
        assert lock_path.is_file()


def test_lock_contention_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    prefix = str(tmp_path / "wine-prefix-2")
    Path(prefix).mkdir()
    result_file = tmp_path / "child.txt"
    proc = multiprocessing.Process(
        target=_hold_lock,
        args=(prefix, "child", 1.5, str(result_file)),
    )
    proc.start()
    time.sleep(0.2)
    from alma_bridge.session.prefix_lock import PrefixLockTimeout

    with pytest.raises(PrefixLockTimeout):
        with prefix_lock(prefix, session_id="parent", timeout_sec=0.3):
            pass
    proc.join(timeout=5)
    assert result_file.read_text(encoding="utf-8") == "held"


def test_different_prefixes_run_concurrently(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    p1 = str(tmp_path / "prefix-a")
    p2 = str(tmp_path / "prefix-b")
    Path(p1).mkdir()
    Path(p2).mkdir()
    with prefix_lock(p1, session_id="a"):
        with prefix_lock(p2, session_id="b"):
            assert True

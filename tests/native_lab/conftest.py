"""Fixtures for native lab tests."""

from __future__ import annotations

import pytest

from alma_bridge.native_lab.queries import NativeLabQueries
from alma_bridge.native_lab.repository import NativeLabRepository
from alma_bridge.native_lab.service import NativeLabService


@pytest.fixture
def native_lab_tmp_paths(tmp_path):
    base = tmp_path / "native_lab"
    return {
        "native_lab": base,
    }


@pytest.fixture
def native_lab_repo(native_lab_tmp_paths):
    return NativeLabRepository(store_dir=native_lab_tmp_paths["native_lab"])


@pytest.fixture
def native_lab_queries(native_lab_repo):
    return NativeLabQueries(repository=native_lab_repo)


@pytest.fixture
def native_lab_service(native_lab_repo, native_lab_queries):
    NativeLabService._instance = None
    service = NativeLabService(repository=native_lab_repo, queries=native_lab_queries)
    return service

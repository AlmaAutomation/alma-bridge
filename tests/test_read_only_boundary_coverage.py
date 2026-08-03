"""Meta coverage for read-only package boundary tests."""

from __future__ import annotations

from tests._boundaries import READ_ONLY_PACKAGES, package_has_boundary_test


def test_all_read_only_packages_have_boundary_tests():
    missing = [pkg for pkg in READ_ONLY_PACKAGES if not package_has_boundary_test(pkg)]
    assert missing == []

"""Compatibility runtime error types."""

from __future__ import annotations


class RuntimeError(Exception):
    """Base class for compatibility runtime errors."""


class RuntimeProviderError(RuntimeError):
    """Raised when a provider operation fails."""


class RuntimeNotSupportedError(RuntimeProviderError):
    """Raised when a provider cannot satisfy a request (fail-closed)."""


class RuntimeRegistryError(RuntimeError):
    """Raised for registry configuration problems."""


class DuplicateProviderError(RuntimeRegistryError):
    """Raised when registering a provider with an existing ID."""


class ProviderNotFoundError(RuntimeRegistryError):
    """Raised when a provider ID is not registered."""

"""Governance-specific errors."""

from __future__ import annotations


class GovernanceError(Exception):
    """Base governance error."""


class PolicyViolationError(GovernanceError):
    """Promotion policy rules not satisfied."""


class StaleProposalError(GovernanceError):
    """Proposal registry version no longer matches current registry."""


class ProposalNotApprovedError(GovernanceError):
    """Proposal lacks approved review or digest mismatch."""


class EvidenceResolutionError(GovernanceError):
    """Supporting calibration evidence cannot be resolved."""


class ScopeMismatchError(GovernanceError):
    """Evidence scope does not match proposal scope."""


class RegistryMutationError(GovernanceError):
    """Attempted invalid registry mutation."""

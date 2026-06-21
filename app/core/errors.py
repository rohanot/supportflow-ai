from __future__ import annotations


class ServiceFlowError(Exception):
    """Base application error."""


class ConfigurationError(ServiceFlowError):
    """Raised when runtime configuration is invalid."""


class NotFoundError(ServiceFlowError):
    """Raised when a requested resource is missing."""


class ConflictError(ServiceFlowError):
    """Raised when a request conflicts with current resource state."""


class LLMUnavailableError(ServiceFlowError):
    """Raised when the LLM provider cannot be reached or returns invalid output."""

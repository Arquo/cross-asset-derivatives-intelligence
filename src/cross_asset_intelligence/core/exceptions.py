"""Custom exceptions for the project."""


class CrossAssetIntelligenceError(Exception):
    """Base exception for the application."""


class ConfigurationError(CrossAssetIntelligenceError):
    """Raised when a provider or config file is invalid."""


class DataValidationError(CrossAssetIntelligenceError):
    """Raised when a record fails validation."""


class ProviderError(CrossAssetIntelligenceError):
    """Raised when a data provider cannot complete an operation."""


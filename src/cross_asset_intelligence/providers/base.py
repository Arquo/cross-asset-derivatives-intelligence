"""Abstract provider interface for data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence

from cross_asset_intelligence.schemas.common import StandardObservation


class DataProvider(ABC):
    """Common contract for all external or synthetic data providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the human-readable provider name."""

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise an exception if the provider configuration is invalid."""

    @abstractmethod
    def fetch(self) -> Sequence[StandardObservation]:
        """Retrieve raw observations from the provider."""

    @abstractmethod
    def normalize(self, observations: Iterable[StandardObservation]) -> Sequence[StandardObservation]:
        """Normalize provider output into canonical observations."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True when the provider is reachable and configured."""


"""Tests for the provider interface and YAML configuration files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from cross_asset_intelligence.providers.base import DataProvider
from cross_asset_intelligence.schemas.common import StandardObservation

from tests.fixtures.sample_records import standard_observation_data


class FakeProvider(DataProvider):
    """Minimal fake provider used to prove the interface works."""

    @property
    def provider_name(self) -> str:
        return "FakeProvider"

    def validate_configuration(self) -> None:
        return None

    def fetch(self) -> list[StandardObservation]:
        return [StandardObservation(**standard_observation_data())]

    def normalize(self, observations: Iterable[StandardObservation]) -> list[StandardObservation]:
        return list(observations)

    def health_check(self) -> bool:
        return True


def test_fake_provider_satisfies_interface():
    provider = FakeProvider()

    assert isinstance(provider, DataProvider)
    assert provider.provider_name == "FakeProvider"
    assert provider.health_check() is True
    assert len(provider.fetch()) == 1


def test_yaml_configuration_files_load_successfully():
    root = Path(__file__).resolve().parents[1]

    assets_path = root / "configs" / "assets.yaml"
    data_sources_path = root / "configs" / "data_sources.yaml"

    with assets_path.open("r", encoding="utf-8") as handle:
        assets = yaml.safe_load(handle)
    with data_sources_path.open("r", encoding="utf-8") as handle:
        data_sources = yaml.safe_load(handle)

    assert "assets" in assets
    assert "providers" in data_sources
    assert len(assets["assets"]["market"]) == 9
    assert all(entry["implementation_status"] == "planned" for entry in data_sources["providers"])


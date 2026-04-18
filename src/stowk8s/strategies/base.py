"""Base protocol and shared types for image discovery strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ImageDependency:
    """Represents a single image found in a chart's dependency tree."""

    source_chart: str
    source_chart_version: str
    image_name: str
    image_tag: str
    source: str
    _sources: list[str] = field(default_factory=list, repr=False)
    _registry: str = field(default="", repr=False)

    @property
    def sources(self) -> list[str]:
        sources = [self.source]
        sources.extend(self._sources)
        return sorted(set(sources))

    @property
    def full_reference(self) -> str:
        """Return the full image reference including registry if available."""
        if self._registry:
            return f"{self._registry}/{self.image_name}:{self.image_tag}"
        return f"{self.image_name}:{self.image_tag}"

    @property
    def registry(self) -> str:
        """Return the dependency registry (e.g. docker.io/bitnami)."""
        return self._registry


class Strategy(Protocol):
    """Interface that all image discovery strategies must implement."""

    name: str

    def find_images(self, chart_dir: Path) -> list[ImageDependency]: ...

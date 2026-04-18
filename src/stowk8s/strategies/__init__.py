"""Strategy manager for image discovery."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from stowk8s.strategies.base import ImageDependency, Strategy

# Module-level registry shared by all StrategyManager instances and @strategy decorators.
_registry: dict[str, type[Strategy]] = {}


def strategy(name: str) -> Callable[[type[Strategy]], type[Strategy]]:
    """Decorator that registers a strategy class."""

    def decorator(cls: type[Strategy]) -> type[Strategy]:
        _registry[name] = cls
        return cls

    return decorator


class StrategyManager:
    """Discovers and dispatches to registered image strategies."""

    def __init__(self) -> None:
        self._registry = _registry

    @property
    def strategies(self) -> list[str]:
        """Return names of all registered strategies."""
        return sorted(self._registry)

    def find_all(self, chart_dir: Path) -> list[ImageDependency]:
        """Instantiate every registered strategy and call find_images(), deduplicating by (image_name, image_tag)."""
        seen: dict[tuple[str, str], ImageDependency] = {}
        for cls in self._registry.values():
            strategy = cls()
            for img in strategy.find_images(chart_dir):
                key = (img.image_name, img.image_tag)
                if key in seen:
                    seen[key]._sources.append(img.source)
                else:
                    seen[key] = img
        return list(seen.values())


# Import built-in strategies so they register themselves at import time.
from stowk8s.strategies import helm_tree, helm_template  # noqa: F401, E402

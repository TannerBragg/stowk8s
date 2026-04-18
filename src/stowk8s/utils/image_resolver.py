"""Resolve image dependencies from Helm chart dependency trees."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from stowk8s.strategies import StrategyManager
from stowk8s.strategies.base import ImageDependency
from stowk8s.strategies.helm_tree import (
    _make_image,
    _parse_helm_images_annotation,
    _parse_images_list,
    extract_local_dependency_path,
    extract_tgz_dependency,
    parse_image_annotations,
    pull_oci_dependency,
)

__all__ = [
    "ImageDependency",
    "check_helm_installed",
    "extract_local_dependency_path",
    "extract_tgz_dependency",
    "parse_image_annotations",
    "pull_oci_dependency",
    "run_dependency_update",
    "walk_dependency_tree",
    "_make_image",
    "_parse_helm_images_annotation",
    "_parse_images_list",
]


def check_helm_installed() -> bool:
    """Check if helm is available on PATH."""
    return shutil.which("helm") is not None


def run_dependency_update(chart_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run helm dependency update against a chart directory.

    Args:
        chart_dir: Path to the Helm chart directory.

    Returns:
        CompletedProcess result from the subprocess call.
    """
    return subprocess.run(
        ["helm", "dependency", "update", str(chart_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )


def walk_dependency_tree(chart_dir: Path) -> list[ImageDependency]:
    """Build chart dependencies, then walk the tree and collect all image dependencies.

    Delegates to all registered strategies for image discovery.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        Deduplicated list of ImageDependency objects.
    """
    # Ensure dependencies are built before any strategy runs
    run_dependency_update(chart_dir)
    return StrategyManager().find_all(chart_dir)

"""Resolve image dependencies from Helm chart dependency trees."""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Any, Dict

from stowk8s.strategies import StrategyManager
from stowk8s.strategies.base import ImageDependency
from stowk8s.strategies.helm_template import HelmTemplateStrategy, _collect_images, _extract_from_containers
from stowk8s.strategies.helm_bsi import (
    _make_image,
    _parse_helm_images_annotation,
    _parse_images_list,
    parse_image_annotations,
    pull_oci_dependency,
)
from stowk8s.utils.helm_utils import check_helm_installed, run_dependency_update
# extract_tgz_dependency and extract_tgz_dependencies have been removed. Use extract_targz and find_and_extract_targz instead.

def extract_tgz_dependency(dep: Dict[str, Any], chart_dir: Path) -> Optional[Path]:
    """Extract a chart dependency tgz file and return the chart directory.

    Args:
        dep: Dictionary with 'name' and 'version' keys.
        chart_dir: Directory where the .tgz file is located.
    Returns:
        Path to the extracted chart directory, or None on error.
    """
    try:
        name = dep.get("name")
        version = dep.get("version")
        if not name or not version:
            raise ValueError("Dependency dict must contain 'name' and 'version'")
        tgz_name = f"{name}-{version}.tgz"
        tgz_path = chart_dir / tgz_name
        if not tgz_path.is_file():
            raise FileNotFoundError(f"Tgz file not found: {tgz_path}")
        # Extract the tarball into chart_dir (same directory as tgz)
        with tarfile.open(tgz_path, "r:gz") as tar:
            tar.extractall(chart_dir)
        # Find the extracted chart directory – the tgz usually extracts to a subdirectory
        # named <name>-<version> under chart_dir.
        for entry in chart_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(f"{name}-{version}"):
                return entry
        # If no subdirectory, maybe the chart is directly at chart_dir
        return chart_dir
    except (FileNotFoundError, ValueError, tarfile.ReadError, OSError):
        return None


from stowk8s.strategies.helm_template import HelmTemplateStrategy, _collect_images, _extract_from_containers
from stowk8s.strategies.helm_bsi import (
    _make_image,
    _parse_helm_images_annotation,
    _parse_images_list,
    parse_image_annotations,
    pull_oci_dependency,
)
from stowk8s.utils.helm_utils import check_helm_installed, run_dependency_update
# extract_tgz_dependency and extract_tgz_dependencies have been removed. Use extract_targz and find_and_extract_targz instead.

__all__ = [
    "ImageDependency",
    "check_helm_installed",
    "run_dependency_update",
    "parse_image_annotations",
    "pull_oci_dependency",
    "walk_dependency_tree",
    "_make_image",
    "_parse_helm_images_annotation",
    "_parse_images_list",
    "extract_tgz_dependency",
]


def walk_dependency_tree(chart_dir: Path) -> list[ImageDependency]:
    """Build chart dependencies, then walk the tree and collect all image dependencies.

    Delegates to all registered strategies for image discovery.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        Deduplicated list of ImageDependency objects.
    """
    return StrategyManager().find_all(chart_dir)
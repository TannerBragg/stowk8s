"""Resolve image dependencies from Helm chart dependency trees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stowk8s.strategies import StrategyManager
from stowk8s.strategies.base import ImageDependency
from stowk8s.strategies.helm_bsi import (
    _make_image,
    _parse_helm_images_annotation,
    _parse_images_list,
    parse_image_annotations,
    pull_oci_dependency,
)
from stowk8s.utils.file_ops import extract_local_dependency_path, extract_tgz_dependencies, extract_tgz_dependency
from stowk8s.utils.helm_utils import check_helm_installed, run_dependency_update

__all__ = [
    "ImageDependency",
    "check_helm_installed",
    "extract_local_dependency_path",
    "extract_tgz_dependency",
    "extract_tgz_dependencies",
    "parse_image_annotations",
    "pull_oci_dependency",
    "run_dependency_update",
    "walk_dependency_tree",
    "_make_image",
    "_parse_helm_images_annotation",
    "_parse_images_list",
]


def walk_dependency_tree(chart_dir: Path) -> list[ImageDependency]:
    """Build chart dependencies, then walk the tree and collect all image dependencies.

    Delegates to all registered strategies for image discovery.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        Deduplicated list of ImageDependency objects.
    """
    run_dependency_update(chart_dir)
    extract_tgz_dependencies(chart_dir)
    return StrategyManager().find_all(chart_dir)

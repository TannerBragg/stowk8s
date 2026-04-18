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
    "extract_tgz_dependencies",
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


def extract_tgz_dependencies(chart_dir: Path) -> list[Path]:
    """Extract all .tgz chart dependencies downloaded by `helm dependency update`.

    Scans charts/ for .tgz files, parses their name/version from the stem
    (e.g. `ingress-nginx-4.15.1.tgz` -> name=ingress-nginx, version=4.15.1),
    extracts each into a persistent directory, deletes the .tgz, and returns
    all chart directories found.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        List of resolved chart directories (both extracted .tgz dirs and existing subdirs).
    """
    charts_dir = chart_dir / "charts"
    if not charts_dir.is_dir():
        return []

    chart_dirs: list[Path] = []
    for child in sorted(charts_dir.iterdir()):
        if child.is_dir():
            chart_dirs.append(child)
        elif child.is_file() and child.name.endswith(".tgz"):
            stem = child.stem  # e.g. ingress-nginx-4.15.1
            last_hyphen = stem.rfind("-")
            if last_hyphen > 0:
                dep_name = stem[:last_hyphen]
                dep_version = stem[last_hyphen + 1:]
            else:
                dep_name = stem
                dep_version = "latest"
            extracted = extract_tgz_dependency({"name": dep_name, "version": dep_version}, charts_dir)
            if extracted and extracted.is_dir():
                chart_dirs.append(extracted)
            child.unlink()

    return chart_dirs


def walk_dependency_tree(chart_dir: Path) -> list[ImageDependency]:
    """Build chart dependencies, then walk the tree and collect all image dependencies.

    Delegates to all registered strategies for image discovery.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        Deduplicated list of ImageDependency objects.
    """
    # Ensure dependencies are built and extracted before any strategy runs
    run_dependency_update(chart_dir)
    extract_tgz_dependencies(chart_dir)
    return StrategyManager().find_all(chart_dir)

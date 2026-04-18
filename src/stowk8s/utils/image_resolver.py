"""Resolve image dependencies from Helm chart dependency trees."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from stowk8s.strategies import StrategyManager
from stowk8s.strategies.base import ImageDependency

from stowk8s.strategies.helm_tree import (
    _make_image,
    _parse_helm_images_annotation,
    _parse_images_list,
    extract_local_dependency_path,
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


def extract_tgz_dependency(dep: dict[str, Any], base_dir: Path) -> Path | None:
    """Extract a single .tgz dependency from charts/ and return path to its Chart.yaml."""

    dep_name = dep.get("name", "")
    dep_version = dep.get("version", "latest")
    charts_dir = base_dir / "charts"

    if not charts_dir.is_dir():
        return None

    tgz_path = charts_dir / f"{dep_name}-{dep_version}.tgz"
    if not tgz_path.exists():
        for child in sorted(charts_dir.iterdir()):
            if child.is_file() and child.name.startswith(f"{dep_name}-") and child.name.endswith(".tgz"):
                tgz_path = child
                break

    if not tgz_path.exists():
        return None

    extract_dir = charts_dir / f".stowk8s-{dep_name}-{dep_version}"
    if not extract_dir.is_dir():
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(tgz_path, "r:gz") as tar:
                tar.extractall(str(extract_dir), filter="data")
        except (tarfile.TarError, OSError) as exc:
            import shutil as _shutil

            _shutil.rmtree(extract_dir, ignore_errors=True)
            return None

    chart_yaml = extract_dir / "Chart.yaml"
    if chart_yaml.exists():
        return extract_dir
    for child in sorted(extract_dir.iterdir()):
        if child.is_dir():
            chart_yaml = child / "Chart.yaml"
            if chart_yaml.exists():
                return child

    return None


def extract_tgz_dependencies(chart_dir: Path) -> list[Path]:
    """Extract any .tgz dependencies in charts/ and return all chart directories."""
    charts_dir = chart_dir / "charts"
    if not charts_dir.is_dir():
        return []

    dirs: list[Path] = []
    for child in sorted(charts_dir.iterdir()):
        if child.is_dir():
            dirs.append(child)
        elif child.is_file() and child.name.endswith(".tgz"):
            stem = child.stem
            target = charts_dir / stem
            if not target.is_dir():
                # Extract to temp dir first, then move up to avoid nested paths
                tmp_dir = target.with_name(target.name + ".tmp")
                with tarfile.open(child, "r:gz") as tar:
                    tar.extractall(str(tmp_dir), filter="data")
                # Move all contents up to target
                for item in tmp_dir.iterdir():
                    shutil.move(str(item), str(target.parent / item.name))
                tmp_dir.rmdir()
            if target.is_dir():
                dirs.append(target)
            child.unlink()

    return dirs

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

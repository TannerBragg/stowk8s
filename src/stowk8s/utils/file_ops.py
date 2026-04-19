"""File operations for Helm chart dependency management."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Any


def extract_local_dependency_path(dep: dict[str, Any], base_dir: Path) -> Path | None:
    """Find a local dependency's Chart.yaml under charts/<name>/ or charts/<name>-<version>/."""
    dep_name = dep.get("name", "")
    dep_version = dep.get("version", "latest")
    charts_dir = base_dir / "charts"

    if not charts_dir.is_dir():
        return None

    for candidate in [charts_dir / f"{dep_name}-{dep_version}", charts_dir / dep_name]:
        chart_yaml = candidate / "Chart.yaml"
        if chart_yaml.exists():
            return chart_yaml

    for child in sorted(charts_dir.iterdir()):
        if child.is_dir() and child.name.startswith(f"{dep_name}-"):
            chart_yaml = child / "Chart.yaml"
            if chart_yaml.exists():
                return child

    return None


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
            shutil.rmtree(extract_dir, ignore_errors=True)
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
                tmp_dir = target.with_name(target.name + ".tmp")
                with tarfile.open(child, "r:gz") as tar:
                    tar.extractall(str(tmp_dir), filter="data")
                for item in tmp_dir.iterdir():
                    shutil.move(str(item), str(target.parent / item.name))
                tmp_dir.rmdir()
            if target.is_dir():
                dirs.append(target)
            child.unlink()

    return dirs

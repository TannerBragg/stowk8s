"""Helm dependency tree image discovery strategy."""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from stowk8s.strategies import strategy
from stowk8s.strategies.base import ImageDependency


def _warn(msg: str) -> None:
    """Print a warning to stderr without using rich (avoid circular import)."""
    print(f"[stowk8s] WARNING: {msg}", file=sys.stderr)


def pull_oci_dependency(dep: dict[str, Any], tmp_dir: Path) -> Path | None:
    """Pull an OCI chart dependency and return path to its Chart.yaml directory."""
    repo = dep.get("repository", "")
    if not repo.startswith("oci://"):
        return None

    version = dep.get("version", "latest")
    dep_name = dep.get("name", "unknown")

    full_url = f"{repo}/{dep_name}"
    cmd = ["helm", "pull", full_url, "--version", version, "--untar", "--destination", str(tmp_dir)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _warn(f"Failed to pull OCI dep {dep.get('name', '?')}: {exc}")
        return None

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        _warn(f"Failed to pull {full_url} (version {version}): {msg}")
        return None

    dep_path = tmp_dir / f"{dep_name}-{version}"
    if dep_path.is_dir():
        return dep_path
    dep_path = tmp_dir / dep_name
    if dep_path.is_dir():
        return dep_path

    dirs = [d for d in tmp_dir.iterdir() if d.is_dir()]
    return dirs[0] if dirs else None


def extract_tgz_dependency(dep: dict[str, Any], base_dir: Path) -> Path | None:
    """Extract a .tgz dependency from charts/ and return path to its Chart.yaml.

    The extracted data is persisted to charts/.stowk8s-{name}-{version}/
    and must be cleaned up by the caller when done.
    """
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
            _warn(f"Failed to extract {tgz_path}: {exc}")
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
                return chart_yaml

    return None


def _run_helm_dependency_update(chart_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run `helm dependency update` against a chart directory."""
    return subprocess.run(
        ["helm", "dependency", "update", str(chart_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )


def resolve_all_dependencies(chart_dir: Path, tmp_dir: Path) -> list[Path]:
    """Run helm dep update and extract all deps, returning chart directories.

    Runs `helm dependency update` which fetches remote deps. Then extracts
    any .tgz files in charts/ and collects all subdirectories.

    Args:
        chart_dir: Root chart directory.
        tmp_dir: Temporary directory for OCI pulls (must already exist).

    Returns:
        List of resolved dependency chart directories.
    """
    deps: list[Path] = []

    # Run helm dep update if Chart.yaml has dependencies
    root_chart = chart_dir / "Chart.yaml"
    if root_chart.exists():
        with open(root_chart) as f:
            chart_data = yaml.safe_load(f) or {}
        if chart_data.get("dependencies"):
            try:
                _run_helm_dependency_update(chart_dir)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    charts_dir = chart_dir / "charts"
    if charts_dir.is_dir():
        for child in sorted(charts_dir.iterdir()):
            if child.is_dir():
                deps.append(child)
            elif child.is_file() and child.name.endswith(".tgz"):
                # Extract: strip .tgz -> "ingress-nginx-4.15.1" -> dep name "ingress-nginx"
                stem = child.stem  # e.g. ingress-nginx-4.15.1
                # Find the last hyphen to split name from version
                last_hyphen = stem.rfind("-")
                if last_hyphen > 0:
                    dep_name = stem[:last_hyphen]
                    dep_version = stem[last_hyphen + 1:]
                else:
                    dep_name = stem
                    dep_version = "latest"
                extracted = extract_tgz_dependency({"name": dep_name, "version": dep_version}, chart_dir)
                if extracted and extracted.is_dir():
                    deps.append(extracted)
                child.unlink()

    # Pull OCI deps that didn't resolve via helm
    if root_chart.exists():
        with open(root_chart) as f:
            chart_data = yaml.safe_load(f) or {}
        for dep in chart_data.get("dependencies", []) or []:
            repo = dep.get("repository", "")
            dep_name = dep.get("name", "unknown")
            dep_version = dep.get("version", "latest")

            if repo.startswith("oci://"):
                dep_path = pull_oci_dependency(dep, tmp_dir)
                if dep_path and dep_path.is_dir():
                    deps.append(dep_path)
            elif not (charts_dir / f"{dep_name}-{dep_version}").is_dir():
                local = extract_local_dependency_path(dep, charts_dir)
                if local and local.is_dir():
                    deps.append(local)

    return deps


def _parse_helm_images_annotation(value: str, chart_name: str, source: str) -> list[ImageDependency]:
    """Parse a JSON or YAML list of images from annotations."""
    images = []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(value)
        except Exception:
            _warn(f"Failed to parse images annotation in {chart_name}")
            return []

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                name = item.get("name", item.get("repo", ""))
                tag = item.get("tag", item.get("version", ""))
            else:
                name = str(item)
                tag = ""
            if name:
                images.append(ImageDependency(source_chart=chart_name, source_chart_version="", image_name=name, image_tag=tag, source=source))
    elif isinstance(parsed, dict):
        name = parsed.get("name", parsed.get("repo", ""))
        tag = parsed.get("tag", parsed.get("version", ""))
        if name:
            images.append(ImageDependency(source_chart=chart_name, source_chart_version="", image_name=str(name), image_tag=str(tag), source=source))
    return images


def _parse_images_list(images: Any, chart_name: str, source: str) -> list[ImageDependency]:
    """Parse a top-level images list field."""
    results = []
    if not isinstance(images, list):
        return results
    for item in images:
        if isinstance(item, dict):
            name = item.get("name", item.get("repo", ""))
            tag = item.get("tag", item.get("version", ""))
        elif isinstance(item, str):
            name = item
            tag = ""
        else:
            continue
        if name:
            results.append(ImageDependency(source_chart=chart_name, source_chart_version="", image_name=str(name), image_tag=str(tag), source=source))
    return results


def _make_image(chart_name: str, value: Any, source: str) -> ImageDependency | None:
    """Create an ImageDependency from a single image value."""
    if isinstance(value, dict):
        name = value.get("name", value.get("repo", ""))
        tag = value.get("tag", value.get("version", ""))
    elif isinstance(value, str):
        name = value
        tag = ""
    else:
        return None
    if name:
        return ImageDependency(source_chart=chart_name, source_chart_version="", image_name=str(name), image_tag=str(tag), source=source)
    return None


def parse_image_annotations(chart_data: dict[str, Any], chart_name: str) -> list[ImageDependency]:
    """Parse a single Chart.yaml for image information."""
    results: list[ImageDependency] = []
    annotations = chart_data.get("annotations", {}) or {}
    chart_version = str(chart_data.get("version", ""))

    for key in ("helm.sh/images", "helm.k8s.io/images"):
        if images := annotations.get(key):
            results.extend(_parse_helm_images_annotation(str(images), chart_name, f"annotations.{key}"))

    if images := annotations.get("images"):
        results.extend(_parse_helm_images_annotation(str(images), chart_name, "annotations.images"))

    for key in ("containerImage",):
        if images := annotations.get(key):
            img = _make_image(chart_name, images, f"annotations.{key}")
            if img:
                results.append(img)

    if image := chart_data.get("image"):
        img = _make_image(chart_name, image, "image")
        if img:
            results.append(img)

    if images := chart_data.get("images"):
        results.extend(_parse_images_list(images, chart_name, "images"))

    for key, val in annotations.items():
        if ".images.helm.sh/" in key and val:
            results.append(ImageDependency(source_chart=chart_name, source_chart_version=chart_version, image_name=str(val), image_tag="", source=f"annotations.{key}"))

    return results


@strategy("bsi")
class HelmTreeStrategy:
    """Discover images by walking Helm chart dependency trees."""

    name = "bsi"

    def find_images(self, chart_dir: Path) -> list[ImageDependency]:
        chart_yaml_path = chart_dir / "Chart.yaml"
        if not chart_yaml_path.exists():
            return []

        with open(chart_yaml_path) as f:
            chart_data = yaml.safe_load(f)
        if not chart_data:
            return []

        return _walk_from_dirs(chart_dir, chart_data)


def _walk_from_dirs(chart_dir: Path, chart_data: dict[str, Any]) -> list[ImageDependency]:
    """Walk the chart's dependency tree and collect images from Chart.yaml annotations.

    Reads dep dirs directly from charts/ on disk (populated by helm dependency update).
    """
    results: list[ImageDependency] = []
    visited: set[str] = set()
    seen_images: dict[tuple[str, str], ImageDependency] = {}

    def _add_image(img: ImageDependency) -> None:
        dedup_key = (img.image_name, img.image_tag)
        if dedup_key in seen_images:
            seen_images[dedup_key]._sources.append(img.source)
        else:
            seen_images[dedup_key] = img
            results.append(img)

    charts_dir = chart_dir / "charts"

    def _scan_dir(dir_path: Path, dep_entry: dict[str, Any]) -> None:
        chart_name = dep_entry.get("name", "unknown")
        chart_version = dep_entry.get("version", "latest")
        key = f"{chart_name}@{chart_version}"
        if key in visited:
            return
        visited.add(key)

        dep_chart = dir_path / "Chart.yaml"
        if not dep_chart.exists():
            return
        with open(dep_chart) as f:
            dep_data = yaml.safe_load(f)
        if not dep_data:
            return

        dep_repo = dep_entry.get("repository", "")
        images = parse_image_annotations(dep_data, chart_name)
        for img in images:
            img.source_chart_version = str(dep_data.get("version", chart_version))
            img._registry = dep_repo
            _add_image(img)

        # Recursively scan nested deps found in charts/
        for sub in dep_data.get("dependencies", []) or []:
            sub_name = sub.get("name", "unknown")
            sub_version = sub.get("version", "latest")
            sub_key = f"{sub_name}@{sub_version}"
            if sub_key in visited:
                continue
            if charts_dir.is_dir():
                for d in charts_dir.iterdir():
                    if d.is_dir() and d.name.startswith(sub_name):
                        _scan_dir(d, sub)
                        break

    # Scan root chart
    root_images = parse_image_annotations(chart_data, str(chart_data.get("name", "unknown")))
    root_version = str(chart_data.get("version", ""))
    for img in root_images:
        img.source_chart_version = root_version
        _add_image(img)

    # Scan each dep entry, matching against dirs in charts/
    for dep in chart_data.get("dependencies", []) or []:
        dep_name = dep.get("name", "unknown")
        dep_version = dep.get("version", "latest")
        dep_key = f"{dep_name}@{dep_version}"
        if dep_key in visited:
            continue
        if charts_dir.is_dir():
            for d in charts_dir.iterdir():
                if d.is_dir() and d.name.startswith(dep_name):
                    _scan_dir(d, dep)
                    break

    return results

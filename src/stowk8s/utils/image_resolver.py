"""Resolve image dependencies from Helm chart dependency trees."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageDependency:
    """Represents a single image found in a chart's dependency tree."""

    source_chart: str
    source_chart_version: str
    image_name: str
    image_tag: str
    source: str
    _sources: list[str] = field(default_factory=list, repr=False)

    @property
    def sources(self) -> list[str]:
        sources = [self.source]
        sources.extend(self._sources)
        return sorted(set(sources))


def _warn(msg: str) -> None:
    """Print a warning to stderr without using rich (avoid circular import)."""
    import sys

    print(f"[stowk8s] WARNING: {msg}", file=sys.stderr)


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


def pull_oci_dependency(dep: dict[str, Any], tmp_dir: Path) -> Path | None:
    """Pull an OCI chart dependency and return path to its Chart.yaml directory.

    Args:
        dep: Dependency dict from Chart.yaml dependencies list.
        tmp_dir: Directory to untar into.

    Returns:
        Path to the untar'd chart directory, or None on failure.
    """
    repo = dep.get("repository", "")
    if not repo.startswith("oci://"):
        return None

    version = dep.get("version", "latest")
    dep_name = dep.get("name", "unknown")

    # For OCI repos, the full URL is oci://<repo>/<name>:<version>
    full_url = f"{repo}/{dep_name}"
    cmd = ["helm", "pull", full_url, "--version", version, "--untar", "--destination", str(tmp_dir)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _warn(f"Failed to pull OCI dep {dep.get('name', '?')}: {exc}")
        return None

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        _warn(f"Failed to pull {full_url} (version {version}): {msg}")
        return None

    # The untar creates a directory named <chart-name>-<version> or just <chart-name>
    dep_path = tmp_dir / f"{dep_name}-{version}"
    if dep_path.is_dir():
        return dep_path
    dep_path = tmp_dir / dep_name
    if dep_path.is_dir():
        return dep_path

    # Fall back: find the only directory in tmp_dir
    dirs = [d for d in tmp_dir.iterdir() if d.is_dir()]
    return dirs[0] if dirs else None


def extract_tgz_dependency(dep: dict[str, Any], base_dir: Path) -> Path | None:
    """Extract a .tgz dependency from charts/ and return path to its Chart.yaml.

    Args:
        dep: Dependency dict from Chart.yaml dependencies list.
        base_dir: Parent directory to search under.

    Returns:
        Path to the Chart.yaml if found, None otherwise.
    """
    dep_name = dep.get("name", "")
    dep_version = dep.get("version", "latest")
    charts_dir = base_dir / "charts"

    if not charts_dir.is_dir():
        return None

    # Find the tgz file
    tgz_path = charts_dir / f"{dep_name}-{dep_version}.tgz"
    if not tgz_path.exists():
        # Try wildcard match for version ranges
        for child in sorted(charts_dir.iterdir()):
            if child.is_file() and child.name.startswith(f"{dep_name}-") and child.name.endswith(".tgz"):
                tgz_path = child
                break

    if not tgz_path.exists():
        return None

    # Extract to a temporary directory within charts/
    tmp_extract = charts_dir / f".stowk8s-{dep_name}-{dep_version}"
    tmp_extract.mkdir(parents=True, exist_ok=True)

    try:
        import tarfile

        with tarfile.open(tgz_path, "r:gz") as tar:
            tar.extractall(str(tmp_extract))
        # Find the Chart.yaml
        chart_yaml = tmp_extract / "Chart.yaml"
        if chart_yaml.exists():
            return chart_yaml
        # Might be nested one level deep
        for child in tmp_extract.iterdir():
            if child.is_dir():
                chart_yaml = child / "Chart.yaml"
                if chart_yaml.exists():
                    return child
    except (tarfile.TarError, OSError) as exc:
        _warn(f"Failed to extract {tgz_path}: {exc}")
    finally:
        shutil.rmtree(tmp_extract, ignore_errors=True)

    return None


def extract_local_dependency_path(dep: dict[str, Any], base_dir: Path) -> Path | None:
    """Find a local dependency's Chart.yaml under charts/<name>/ or charts/<name>-<version>/.

    Args:
        dep: Dependency dict from Chart.yaml dependencies list.
        base_dir: Parent directory to search under.

    Returns:
        Path to the Chart.yaml if found, None otherwise.
    """
    dep_name = dep.get("name", "")
    dep_version = dep.get("version", "latest")
    charts_dir = base_dir / "charts"

    if not charts_dir.is_dir():
        return None

    # Try name-version pattern first
    candidates = [
        charts_dir / f"{dep_name}-{dep_version}",
        charts_dir / dep_name,
    ]
    for candidate in candidates:
        chart_yaml = candidate / "Chart.yaml"
        if chart_yaml.exists():
            return chart_yaml

    # Wildcard match for version ranges (e.g. dep_version = ">=1.0.0")
    for child in sorted(charts_dir.iterdir()):
        if child.is_dir() and child.name.startswith(f"{dep_name}-"):
            chart_yaml = child / "Chart.yaml"
            if chart_yaml.exists():
                return chart_yaml

    return None


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
                images.append(
                    ImageDependency(
                        source_chart=chart_name,
                        source_chart_version="",
                        image_name=name,
                        image_tag=tag,
                        source=source,
                    )
                )
    elif isinstance(parsed, dict):
        name = parsed.get("name", parsed.get("repo", ""))
        tag = parsed.get("tag", parsed.get("version", ""))
        if name:
            images.append(
                ImageDependency(
                    source_chart=chart_name,
                    source_chart_version="",
                    image_name=str(name),
                    image_tag=str(tag),
                    source=source,
                )
            )
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
            results.append(
                ImageDependency(
                    source_chart=chart_name,
                    source_chart_version="",
                    image_name=str(name),
                    image_tag=str(tag),
                    source=source,
                )
            )
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
        return ImageDependency(
            source_chart=chart_name,
            source_chart_version="",
            image_name=str(name),
            image_tag=str(tag),
            source=source,
        )
    return None


def parse_image_annotations(chart_data: dict[str, Any], chart_name: str) -> list[ImageDependency]:
    """Parse a single Chart.yaml for image information.

    Tries multiple annotation patterns in priority order.
    """
    results: list[ImageDependency] = []
    annotations = chart_data.get("annotations", {}) or {}
    chart_version = str(chart_data.get("version", ""))

    # Pattern: annotations["helm.sh/images"] or "helm.k8s.io/images" -> JSON/YAML list
    for key in ("helm.sh/images", "helm.k8s.io/images"):
        if images := annotations.get(key):
            results.extend(_parse_helm_images_annotation(str(images), chart_name, f"annotations.{key}"))

    # Pattern: annotations["images"] -> YAML/JSON list (Bitnami style)
    if images := annotations.get("images"):
        results.extend(_parse_helm_images_annotation(str(images), chart_name, "annotations.images"))

    # Pattern: single container image annotations
    for key in ("containerImage",):
        if images := annotations.get(key):
            img = _make_image(chart_name, images, f"annotations.{key}")
            if img:
                results.append(img)

    # Pattern: direct image.name / image.tag fields
    if image := chart_data.get("image"):
        img = _make_image(chart_name, image, "image")
        if img:
            results.append(img)

    # Pattern: direct images: list
    if images := chart_data.get("images"):
        results.extend(_parse_images_list(images, chart_name, "images"))

    # Pattern: reverse-domain annotations like images.helm.sh/repo/name
    for key, val in annotations.items():
        if ".images.helm.sh/" in key and val:
            results.append(
                ImageDependency(
                    source_chart=chart_name,
                    source_chart_version=chart_version,
                    image_name=str(val),
                    image_tag="",
                    source=f"annotations.{key}",
                )
            )

    return results


def walk_dependency_tree(chart_dir: Path) -> list[ImageDependency]:
    """Walk a chart's dependency tree and collect all image dependencies.

    Args:
        chart_dir: Path to the root chart directory.

    Returns:
        Deduplicated list of ImageDependency objects.
    """
    chart_yaml_path = chart_dir / "Chart.yaml"
    if not chart_yaml_path.exists():
        return []

    with open(chart_yaml_path) as f:
        chart_data = yaml.safe_load(f)

    if not chart_data:
        return []

    # Use a temp directory for OCI fetches
    tmp_dir = Path(tempfile.mkdtemp(prefix=".stowk8s-"))
    try:
        return _walk(chart_data, chart_dir, tmp_dir)
    finally:
        import shutil as _shutil
        _shutil.rmtree(tmp_dir, ignore_errors=True)


def _walk(chart_data: dict[str, Any], chart_dir: Path, tmp_dir: Path) -> list[ImageDependency]:
    """Internal walker implementation."""
    results: list[ImageDependency] = []
    visited: set[str] = set()
    seen_images: dict[tuple[str, str], ImageDependency] = {}

    def _resolve(dep: dict[str, Any]) -> None:
        chart_name = dep.get("name", "unknown")
        chart_version = dep.get("version", "latest")
        key = f"{chart_name}@{chart_version}"
        if key in visited:
            return
        visited.add(key)

        dep_path = None
        if dep.get("repository", "").startswith("oci://"):
            dep_path = pull_oci_dependency(dep, Path(tmp_dir))
        else:
            tgz = extract_tgz_dependency(dep, chart_dir)
            if tgz:
                dep_path = tgz.parent
            else:
                local = extract_local_dependency_path(dep, chart_dir)
                if local:
                    dep_path = local.parent

        if dep_path and (dep_chart := dep_path / "Chart.yaml").exists():
            with open(dep_chart) as f:
                dep_data = yaml.safe_load(f)
            if dep_data:
                images = parse_image_annotations(dep_data, chart_name)
                for img in images:
                    img.source_chart_version = str(dep_data.get("version", chart_version))
                    _add_image(img)
                # Recurse into sub-dependencies
                for sub in dep_data.get("dependencies", []) or []:
                    _resolve(sub)

    def _add_image(img: ImageDependency) -> None:
        dedup_key = (img.image_name, img.image_tag)
        if dedup_key in seen_images:
            seen_images[dedup_key]._sources.append(img.source)
        else:
            seen_images[dedup_key] = img
            results.append(img)

    # Parse root chart
    root_images = parse_image_annotations(chart_data, str(chart_data.get("name", "unknown")))
    for img in root_images:
        img.source_chart_version = str(chart_data.get("version", ""))
        _add_image(img)

    # Walk dependencies
    for dep in chart_data.get("dependencies", []) or []:
        _resolve(dep)

    return results

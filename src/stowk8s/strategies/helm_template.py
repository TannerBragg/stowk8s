"""Image discovery via `helm template` rendering."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from stowk8s.strategies import strategy
from stowk8s.strategies.base import ImageDependency


def _warn(msg: str) -> None:
    print(f"[stowk8s] WARNING: {msg}", file=sys.stderr)


@strategy("helm-template")
class HelmTemplateStrategy:
    """Discover images by rendering the chart with `helm template`."""

    name = "helm-template"

    def find_images(self, chart_dir: Path) -> list[ImageDependency]:
        try:
            result = subprocess.run(
                ["helm", "template", "release", str(chart_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            _warn(f"helm template timed out: {exc}")
            return []

        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            _warn(f"helm template failed: {stderr}")
            return []

        documents = list(yaml.safe_load_all(result.stdout))
        return _collect_images(documents)


def _parse_chart_yaml(chart_data: dict[str, Any], chart_name: str, chart_version: str) -> list[ImageDependency]:
    """Parse a Chart.yaml for image information."""
    images: list[ImageDependency] = []
    annotations = chart_data.get("annotations", {}) or {}

    for key in ("helm.sh/images", "helm.k8s.io/images"):
        if val := annotations.get(key):
            images.extend(_parse_image_value(str(val), chart_name, f"annotations.{key}", chart_version))

    if val := annotations.get("images"):
        images.extend(_parse_image_value(str(val), chart_name, "annotations.images", chart_version))

    for key in ("containerImage",):
        if val := annotations.get(key):
            img = _make_image(chart_name, val, f"annotations.{key}", chart_version)
            if img:
                img.source_chart_version = chart_version
                images.append(img)

    if val := chart_data.get("image"):
        img = _make_image(chart_name, val, "image", chart_version)
        if img:
            img.source_chart_version = chart_version
            images.append(img)

    if val := chart_data.get("images"):
        images.extend(_parse_images_list(val, chart_name, "images", chart_version))

    return images


def _make_image(chart_name: str, value: Any, source: str, chart_version: str = "") -> ImageDependency | None:
    if isinstance(value, dict):
        name = value.get("name", value.get("repo", ""))
        tag = value.get("tag", value.get("version", ""))
    elif isinstance(value, str):
        name = value
        tag = ""
    else:
        return None
    if name:
        # Extract tag from name if present and tag is empty
        if not tag and ':' in name:
            name_part, tag_part = name.rsplit(':', 1)
            name = name_part
            tag = tag_part
        # Ensure the image reference is prefixed with the OCI scheme
        if not name.startswith("oci://"):
            name = f"oci://{name}"
        return ImageDependency(
            source_chart=chart_name,
            source_chart_version=chart_version,
            image_name=str(name),
            image_tag=str(tag),
            source=source,
        )
    return None


def _parse_image_value(value: str, chart_name: str, source: str, chart_version: str = "") -> list[ImageDependency]:
    """Parse a JSON or YAML list from a string."""
    images: list[ImageDependency] = []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(value)
        except Exception:
            _warn(f"Failed to parse images annotation in {chart_name}")
            return images

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                name = item.get("name", item.get("repo", ""))
                tag = item.get("tag", item.get("version", ""))
            else:
                name = str(item)
                tag = ""
            if name:
                # Extract tag from name if present and tag is empty
                if not tag and ':' in name:
                    name_part, tag_part = name.rsplit(':', 1)
                    name = name_part
                    tag = tag_part
                # Ensure the image reference is prefixed with the OCI scheme
                if not name.startswith("oci://"):
                    name = f"oci://{name}"
                images.append(ImageDependency(
                    source_chart=chart_name,
                    source_chart_version=chart_version,
                    image_name=str(name),
                    image_tag=str(tag),
                    source=source,
                ))
    elif isinstance(parsed, dict):
        name = parsed.get("name", parsed.get("repo", ""))
        tag = parsed.get("tag", parsed.get("version", ""))
        if name:
            if not name.startswith("oci://"):
                name = f"oci://{name}"
            images.append(ImageDependency(
                source_chart=chart_name,
                source_chart_version=chart_version,
                image_name=str(name),
                image_tag=str(tag),
                source=source,
            ))
    return images


def _parse_images_list(images: Any, chart_name: str, source: str, chart_version: str = "") -> list[ImageDependency]:
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
            # Extract tag from name if present and tag is empty
            if not tag and ':' in name:
                name_part, tag_part = name.rsplit(':', 1)
                name = name_part
                tag = tag_part
            # Ensure the image reference is prefixed with the OCI scheme
            if not name.startswith("oci://"):
                name = f"oci://{name}"
            results.append(ImageDependency(
                source_chart=chart_name,
                source_chart_version=chart_version,
                image_name=str(name),
                image_tag=str(tag),
                source=source,
            ))
    return results


_CONTAINER_PATHS = ["containers", "initContainers", "ephemeralContainers"]


def _collect_images(documents: list[Any]) -> list[ImageDependency]:
    images: list[ImageDependency] = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "")
        if kind not in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"):
            continue
        if kind == "CronJob":
            spec = (((doc.get("spec") or {}).get("jobTemplate") or {}).get("spec")) or {}
        elif kind in ("Job", "Pod"):
            spec = ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
            if kind == "Pod" and not spec:
                spec = doc.get("spec") or {}
        else:
            spec = (((doc.get("spec") or {}).get("template") or {}).get("spec")) or {}

        source = f"{doc.get('kind', 'Unknown')}/{doc.get('metadata', {}).get('name', '?')}"
        labels = (doc.get("metadata") or {}).get("labels", {}) or {}
        helm_chart = labels.get("helm.sh/chart", "")
        chart_name = ""
        chart_version = ""
        if helm_chart:
            last_hyphen = helm_chart.rfind("-")
            if last_hyphen > 0:
                chart_name = helm_chart[:last_hyphen]
                chart_version = helm_chart[last_hyphen + 1:]
        for key in _CONTAINER_PATHS:
            _extract_from_containers(spec.get(key, []) or [], source, images, chart_name, chart_version)
    return images


def _extract_from_containers(
    containers: list[Any], source: str, images: list[ImageDependency],
    chart_name: str = "", chart_version: str = "",
) -> None:
    for c in containers:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", ""))
        image = str(c.get("image", ""))
        if not name or not image:
            continue
        if ":" in image:
            parts = image.rsplit(":", 1)
            img_name, tag = parts[0], parts[1]
        else:
            img_name, tag = image, ""
        if not img_name.startswith("oci://"):
            img_name = f"oci://{img_name}"
        images.append(ImageDependency(
            source_chart=chart_name,
            source_chart_version=chart_version,
            image_name=img_name,
            image_tag=tag,
            source=source,
        ))
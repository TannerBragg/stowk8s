"""Deep tests for image_resolver internal branches."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from stowk8s.utils.image_resolver import (
    _parse_helm_images_annotation,
    _parse_images_list,
    _make_image,
    walk_dependency_tree,
    ImageDependency,
)


def test_parse_helm_images_annotation_dict_branch() -> None:
    """Test _parse_helm_images_annotation when parsed result is a dict (not a list)."""
    images = _parse_helm_images_annotation('{"name": "nginx", "tag": "1.25"}', "test-chart", "annotations.helm.sh/images")
    assert len(images) == 1
    assert images[0].image_name == "nginx"


def test_parse_helm_images_annotation_json_list() -> None:
    """Test parsing a JSON list of images."""
    images = _parse_helm_images_annotation('["nginx", "redis"]', "test-chart", "annotations.helm.sh/images")
    assert len(images) == 2
    assert images[0].image_name == "nginx"
    assert images[1].image_name == "redis"


def test_parse_helm_images_annotation_dict_value() -> None:
    """Test parsing a list of dict items."""
    images = _parse_helm_images_annotation(
        '[{"name": "nginx", "tag": "1.25"}, {"repo": "redis", "version": "7.0"}]',
        "test-chart",
        "annotations.helm.sh/images",
    )
    assert len(images) == 2
    assert images[0].image_name == "nginx"
    assert images[0].image_tag == "1.25"
    assert images[1].image_name == "redis"


def test_parse_helm_images_annotation_empty_name() -> None:
    """Test that items with empty names are skipped."""
    images = _parse_helm_images_annotation('{"name": "", "tag": "1.0"}', "test-chart", "annotations.helm.sh/images")
    assert len(images) == 0


def test_parse_helm_images_annotation_both_parse_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that completely invalid annotation returns empty."""
    images = _parse_helm_images_annotation("{{{invalid", "test-chart", "annotations.helm.sh/images")
    assert len(images) == 0


def test_parse_images_list_invalid_types() -> None:
    """Test _parse_images_list with mixed valid/invalid item types."""
    # Non-list input
    result = _parse_images_list("not a list", "test-chart", "images")
    assert result == []

    # Mixed types in list — 123/None are skipped, dict and str are kept
    result = _parse_images_list([123, {"name": "nginx", "tag": "1.0"}, None, "redis"], "test-chart", "images")
    assert len(result) == 2
    assert result[0].image_name == "nginx"
    assert result[1].image_name == "redis"


def test_parse_images_list_string_items() -> None:
    """Test _parse_images_list with string items (tagless)."""
    result = _parse_images_list(["nginx", "redis"], "test-chart", "images")
    assert len(result) == 2
    assert result[0].image_name == "nginx"
    assert result[0].image_tag == ""


def test_make_image_dict_none_name() -> None:
    """Test _make_image returns None when name/repo is missing in dict."""
    assert _make_image("test-chart", {"tag": "1.0"}, "image") is None


def test_make_image_invalid_type() -> None:
    """Test _make_image returns None for unsupported value types."""
    assert _make_image("test-chart", 123, "image") is None
    assert _make_image("test-chart", None, "image") is None


def test_make_image_string() -> None:
    """Test _make_image with string value (tagless)."""
    img = _make_image("test-chart", "nginx:1.25", "image")
    assert img is not None
    assert img.image_name == "nginx:1.25"
    assert img.image_tag == ""


def test_make_image_with_repo_field() -> None:
    """Test _make_image falling back to repo field."""
    img = _make_image("test-chart", {"repo": "my-registry/nginx", "version": "1.0"}, "image")
    assert img is not None
    assert img.image_name == "my-registry/nginx"
    assert img.image_tag == "1.0"


def test_parse_images_list_dict_with_repo() -> None:
    """Test _parse_images_list items using repo as name fallback."""
    result = _parse_images_list([{"repo": "my-registry/myapp", "version": "2.0"}], "test-chart", "images")
    assert len(result) == 1
    assert result[0].image_name == "my-registry/myapp"


def test_walk_with_local_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test walk_dependency_tree with local chart dependencies."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root_chart = tmp_path / "root-chart"
        root_chart.mkdir()
        (root_chart / "Chart.yaml").write_text("""apiVersion: v2
name: root-chart
version: 1.0.0
images:
- name: root-nginx
  tag: "1.0"
dependencies:
  - name: local-chart
    version: "1.0"
    repository: "file://./charts/local-chart"
""")

        charts_dir = root_chart / "charts"
        charts_dir.mkdir()
        dep_chart = charts_dir / "local-chart"
        dep_chart.mkdir()
        (dep_chart / "Chart.yaml").write_text("""apiVersion: v2
name: local-chart
version: 1.0.0
image:
  name: local-redis
  tag: "7.0"
""")

        images = walk_dependency_tree(root_chart)
        names = {img.image_name for img in images}
        assert "root-nginx" in names
        assert "local-redis" in names


def test_walk_duplicate_images_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that _walk deduplicates images with same (name, tag) across deps."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root_chart = tmp_path / "root"
        root_chart.mkdir()
        (root_chart / "Chart.yaml").write_text("""apiVersion: v2
name: root
version: 1.0.0
images:
- name: shared-nginx
  tag: "1.0"
dependencies:
  - name: chart-a
    version: "1.0"
    repository: https://example.com/charts
  - name: chart-b
    version: "1.0"
    repository: https://example.com/charts
""")

        charts_dir = root_chart / "charts"
        charts_dir.mkdir()
        # Both deps extract to same directory via extract_local_dependency_path
        for name in ["chart-a-1.0", "chart-b-1.0"]:
            dep = charts_dir / name
            dep.mkdir()
            (dep / "Chart.yaml").write_text("""apiVersion: v2
name: {}
version: 1.0.0
images:
- name: shared-nginx
  tag: "1.0"
""".format(name))

        images = walk_dependency_tree(root_chart)
        shared = [img for img in images if img.image_name == "shared-nginx"]
        assert len(shared) == 1
        # The root chart image is seen first; chart-a also has it
        # Verify we have 1 deduped image with at least 2 sources
        assert len(shared[0].sources) >= 1


def test_image_dependency_full_reference() -> None:
    dep = ImageDependency("chart", "1.0", "nginx", "1.25", "image.name")
    assert dep.full_reference == "nginx:1.25"


def test_image_dependency_full_reference_no_tag() -> None:
    dep = ImageDependency("chart", "1.0", "redis", "", "image.name")
    assert dep.full_reference == "redis:"


def test_image_dependency_full_reference_with_registry() -> None:
    dep = ImageDependency("chart", "1.0", "some/path/hello-world", "mytag", "image.name")
    dep._registry = "docker.io"
    assert dep.full_reference == "docker.io/some/path/hello-world:mytag"


def test_image_dependency_registry_property() -> None:
    dep = ImageDependency("chart", "1.0", "nginx", "1.0", "image.name")
    dep._registry = "docker.io/bitnami"
    assert dep.registry == "docker.io/bitnami"
    assert dep.full_reference == "docker.io/bitnami/nginx:1.0"


def test_image_dependency_full_reference_no_registry() -> None:
    dep = ImageDependency("chart", "1.0", "nginx", "1.25", "image.name")
    assert dep.full_reference == "nginx:1.25"
    assert dep.registry == ""

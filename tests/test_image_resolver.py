"""Tests for the image_resolver module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import io
import pytest

from stowk8s.utils.image_resolver import (
    check_helm_installed,
    run_dependency_update,
    pull_oci_dependency,
    parse_image_annotations,
    walk_dependency_tree,
    ImageDependency,
)
from stowk8s.utils.file_ops import extract_targz, find_and_extract_targz
from stowk8s.strategies.helm_template import HelmTemplateStrategy, _collect_images, _extract_from_containers


def test_check_helm_installed_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("stowk8s.utils.helm_utils.shutil.which", lambda x: "/usr/bin/helm")
    assert check_helm_installed() is True


def test_check_helm_installed_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("stowk8s.utils.helm_utils.shutil.which", lambda x: None)
    assert check_helm_installed() is False


def test_run_dependency_update(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(["helm", "dep", "up"], 0, "ok", ""))
    monkeypatch.setattr("stowk8s.utils.helm_utils.subprocess.run", mock_run)
    result = run_dependency_update(Path("/fake"))
    assert result.returncode == 0
    mock_run.assert_called_once()
    assert "helm" in mock_run.call_args[0][0][0]


def test_pull_oci_non_oci(monkeypatch: pytest.MonkeyPatch) -> None:
    dep = {"name": "test", "repository": "https://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        assert pull_oci_dependency(dep, Path(tmp)) is None


def test_pull_oci_success(monkeypatch: pytest.MonkeyPatch) -> None:
    dep = {"name": "my-chart", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "my-chart-1.0.0").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
            result = pull_oci_dependency(dep, tmp_path)
            assert result is not None
            assert "my-chart-1.0.0" in str(result)


def test_pull_oci_subprocess_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    dep = {"name": "my-chart", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("Result", (), {"returncode": 1, "stderr": "failed", "stdout": ""})()
            result = pull_oci_dependency(dep, Path(tmp))
            assert result is None


def test_pull_oci_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    dep = {"name": "my-chart", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("helm", 120)):
            result = pull_oci_dependency(dep, Path(tmp))
            assert result is None


def test_pull_oci_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    dep = {"name": "my-chart", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = pull_oci_dependency(dep, Path(tmp))
            assert result is None


def test_pull_oci_fallback_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fallback when name-version dir doesn't exist."""
    dep = {"name": "my-chart", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create just name dir
        (tmp_path / "my-chart").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
            result = pull_oci_dependency(dep, tmp_path)
            assert result is not None
            assert "my-chart" in str(result)


def test_pull_oci_fallback_only_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fallback to single dir in tmp."""
    dep = {"name": "orphan", "version": "1.0.0", "repository": "oci://example.com/charts"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "orphan-subdir").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
            result = pull_oci_dependency(dep, tmp_path)
            assert result is not None


def test_extract_tgz_no_charts_dir(tmp_path: Path) -> None:
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    # No chart directory, so no tgz file to extract
    # Using extract_targz will raise FileNotFoundError if tgz file doesn't exist
    tgz_path = charts_dir / f"{dep['name']}-{dep['version']}.tgz"
    try:
        extract_targz(tgz_path)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_extract_tgz_no_tgz_file(tmp_path: Path) -> None:
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    # No .tgz file present
    tgz_path = charts_dir / f"{dep['name']}-{dep['version']}.tgz"
    try:
        extract_targz(tgz_path)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_extract_tgz_success(tmp_path: Path) -> None:
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    # Create a fake tgz with Chart.yaml inside
    import tarfile
    tgz_path = charts_dir / "my-chart-1.0.0.tgz"
    with tarfile.open(tgz_path, "w:gz") as tar:
        # Add a file that simulates Chart.yaml in root of tar
        data = b"apiVersion: v2\nname: my-chart\n"
        info = tarfile.TarInfo(name="Chart.yaml")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    result = extract_tgz_dependency(dep, tmp_path)
    assert result is not None
    assert result.is_dir()
    assert (result / "Chart.yaml").exists()


def test_extract_tgz_wildcard_match(tmp_path: Path) -> None:
    """Test wildcard version matching for tgz files."""
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    import tarfile
    tgz_path = charts_dir / "my-chart-2.0.0.tgz"
    with tarfile.open(tgz_path, "w:gz") as tar:
        data = b"apiVersion: v2\nname: my-chart\n"
        info = tarfile.TarInfo(name="Chart.yaml")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    result = extract_tgz_dependency(dep, tmp_path)
    assert result is not None


def test_extract_tgz_nested(tmp_path: Path) -> None:
    """Test extraction where Chart.yaml is in a nested directory."""
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    import tarfile
    tgz_path = charts_dir / "my-chart-1.0.0.tgz"
    with tarfile.open(tgz_path, "w:gz") as tar:
        data = b"apiVersion: v2\nname: my-chart\n"
        info = tarfile.TarInfo(name="my-chart-1.0.0/Chart.yaml")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    result = extract_tgz_dependency(dep, tmp_path)
    assert result is not None
    assert "Chart.yaml" in str(result) or "my-chart-1.0.0" in str(result)


def test_extract_tgz_bad_tarfile(tmp_path: Path) -> None:
    """Test handling of corrupt tarball."""
    dep = {"name": "my-chart", "version": "1.0.0"}
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    # Write invalid gzip data
    tgz_path = charts_dir / "my-chart-1.0.0.tgz"
    tgz_path.write_bytes(b"not-a-tarball")
    result = extract_tgz_dependency(dep, tmp_path)
    assert result is None




def test_parse_image_annotations_helm_sh_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing helm.sh/images annotation."""
    chart_data = {
        "name": "test-chart",
        "annotations": {
            "helm.sh/images": '[{"name": "nginx", "tag": "1.25"}]'
        },
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 1
    assert images[0].image_name == "nginx"
    assert images[0].image_tag == "1.25"


def test_parse_image_annotations_container_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test containerImage annotation."""
    chart_data = {
        "name": "test-chart",
        "annotations": {
            "containerImage": "nginx:1.25",
        },
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 1
    assert images[0].image_name == "nginx:1.25"


def test_parse_image_annotations_direct_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test direct image field."""
    chart_data = {
        "name": "test-chart",
        "image": {"name": "myapp", "tag": "2.0"},
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 1
    assert images[0].image_name == "myapp"
    assert images[0].image_tag == "2.0"


def test_parse_image_annotations_direct_images_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test direct images list field."""
    chart_data = {
        "name": "test-chart",
        "images": [{"name": "app1", "tag": "1.0"}, {"name": "app2", "tag": "2.0"}],
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 2
    assert images[0].image_name == "app1"
    assert images[1].image_name == "app2"


def test_parse_image_annotations_reverse_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reverse-domain annotation."""
    chart_data = {
        "name": "test-chart",
        "version": "1.0.0",
        "annotations": {
            "foo.images.helm.sh/repo/name": "nginx:1.25",
        },
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 1
    assert images[0].image_name == "nginx:1.25"


def test_parse_image_annotations_no_annotations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test chart with no annotations returns empty."""
    chart_data = {"name": "test-chart"}
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 0


def test_parse_image_annotations_json_helm_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing JSON list from helm.k8s.io/images."""
    chart_data = {
        "name": "test-chart",
        "annotations": {
            "helm.k8s.io/images": '["nginx", "redis"]',
        },
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 2
    assert images[0].image_name == "nginx"
    assert images[1].image_name == "redis"


def test_parse_image_annotations_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test invalid annotation value is handled gracefully."""
    chart_data = {
        "name": "test-chart",
        "annotations": {
            "helm.sh/images": "not valid json or yaml [[[",
        },
    }
    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 0


def test_walk_dependency_tree_no_chart_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = walk_dependency_tree(Path(tmp))
        assert result == []


def test_walk_dependency_tree_empty_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        chart_yaml = Path(tmp) / "Chart.yaml"
        chart_yaml.write_text("apiVersion: v2\nname: test\n")
        result = walk_dependency_tree(Path(tmp))
        assert result == []


def test_walk_dependency_tree_with_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        chart_yaml = Path(tmp) / "Chart.yaml"
        chart_yaml.write_text("""apiVersion: v2
name: test-chart
version: 1.0.0
images:
- name: nginx
  tag: "1.25"
""")
        result = walk_dependency_tree(Path(tmp))
        assert len(result) == 1
        assert result[0].image_name == "nginx"
        assert result[0].image_tag == "1.25"
        assert result[0].source_chart == "test-chart"


def test_walk_dependency_tree_null_chart_data(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        chart_yaml = Path(tmp) / "Chart.yaml"
        chart_yaml.write_text("---\n")
        result = walk_dependency_tree(Path(tmp))
        assert result == []


def test_image_dependency_sources_property() -> None:
    dep = ImageDependency("chart", "1.0", "nginx", "1.25", "image.name")
    dep._sources.append("annotations.helm.sh/images")
    sources = dep.sources
    assert sources == ["annotations.helm.sh/images", "image.name"]


def test_image_dependency_sources_dedup() -> None:
    dep = ImageDependency("chart", "1.0", "nginx", "1.25", "image.name")
    dep._sources.append("image.name")
    sources = dep.sources
    assert sources == ["image.name"]


# --- helm-template strategy tests ---


def test_collect_images_deployment() -> None:
    doc = {
        "kind": "Deployment",
        "metadata": {"name": "my-deploy"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [{"name": "web", "image": "nginx:1.25"}, {"name": "sidecar", "image": "envoy:v1.28"}],
                    "initContainers": [{"name": "init", "image": "busybox:1.36"}],
                }
            }
        },
    }
    images = _collect_images([doc])
    assert len(images) == 3
    names = {(i.image_name, i.image_tag) for i in images}
    assert ("nginx", "1.25") in names
    assert ("envoy", "v1.28") in names
    assert ("busybox", "1.36") in names


def test_collect_images_cronjob() -> None:
    doc = {
        "kind": "CronJob",
        "metadata": {"name": "backup"},
        "spec": {
            "jobTemplate": {
                "spec": {
                    "containers": [{"name": "backup-ctr", "image": "restic/restic:0.16"}],
                }
            }
        },
    }
    images = _collect_images([doc])
    assert len(images) == 1
    assert images[0].image_name == "restic/restic"
    assert images[0].image_tag == "0.16"


def test_collect_images_pod() -> None:
    doc = {
        "kind": "Pod",
        "metadata": {"name": "debug-pod"},
        "spec": {"containers": [{"name": "shell", "image": "alpine:3.18"}]},
    }
    images = _collect_images([doc])
    assert len(images) == 1


def test_collect_images_unsupported_kind() -> None:
    doc = {"kind": "Service", "metadata": {"name": "svc"}}
    images = _collect_images([doc])
    assert images == []


def test_collect_images_no_image_field() -> None:
    doc = {
        "kind": "Deployment",
        "metadata": {"name": "x"},
        "spec": {"template": {"spec": {"containers": [{"name": "c"}]}}},
    }
    images = _collect_images([doc])
    assert images == []


def test_collect_images_empty_doc() -> None:
    images = _collect_images([None])
    assert images == []

    images = _collect_images([])
    assert images == []


def test_helm_template_strategy_success(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_dir = Path(tempfile.mkdtemp())
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nname: test\n")

    output = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: release-test
spec:
  template:
    spec:
      containers:
      - name: app
        image: myregistry.io/app:2.1
"""
    mock_result = type("Result", (), {"returncode": 0, "stderr": "", "stdout": output})()
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

    strategy = HelmTemplateStrategy()
    images = strategy.find_images(chart_dir)
    assert len(images) == 1
    assert images[0].image_name == "myregistry.io/app"
    assert images[0].image_tag == "2.1"


def test_helm_template_strategy_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_dir = Path(tempfile.mkdtemp())
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nname: test\n")

    mock_result = type("Result", (), {"returncode": 1, "stderr": "helm error", "stdout": ""})()
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

    strategy = HelmTemplateStrategy()
    images = strategy.find_images(chart_dir)
    assert images == []


def test_helm_template_strategy_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_dir = Path(tempfile.mkdtemp())
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nname: test\n")

    mock = MagicMock(side_effect=subprocess.TimeoutExpired(["helm"], 120))
    monkeypatch.setattr("stowk8s.strategies.helm_template.subprocess.run", mock)

    strategy = HelmTemplateStrategy()
    images = strategy.find_images(chart_dir)
    assert images == []

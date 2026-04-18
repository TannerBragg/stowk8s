"""Tests for the image command group."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from stowk8s.cli import main
from stowk8s.utils.image_resolver import ImageDependency

runner = CliRunner()
SAMPLE_CHARTS = Path(__file__).parent.parent / "sample"


def test_image_list_invalid_dir() -> None:
    """Test that a non-existent chart directory returns exit code 1."""
    result = runner.invoke(main, ["image", "list", "-C", "/nonexistent/path"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_image_list_no_helm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that image list fails gracefully when helm is missing."""
    monkeypatch.setattr("stowk8s.utils.image_resolver.check_helm_installed", lambda: False)
    result = runner.invoke(main, ["image", "list", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 1
    assert "helm is not installed" in result.stdout


def test_image_list_with_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that image list outputs a table when images are found."""
    monkeypatch.setattr("stowk8s.commands.image.check_helm_installed", lambda: True)
    fake_result = type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
    monkeypatch.setattr("stowk8s.commands.image.run_dependency_update", lambda *a: fake_result)
    fake_images = [
        ImageDependency("sample-app", "0.1.0", "nginx", "1.25", "image.name"),
        ImageDependency("nginx-ingress", "4.15.1", "registry.k8s.io/ingress-nginx/controller", "v1.12.1", "annotations.helm.sh/images"),
    ]
    monkeypatch.setattr("stowk8s.commands.image.walk_dependency_tree", lambda *a: fake_images)
    result = runner.invoke(main, ["image", "list", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 0
    assert "Image Dependencies" in result.stdout
    assert "nginx" in result.stdout  # appears in Chart and Image columns
    assert "sample-app" in result.stdout
    assert "nginx-ingress" in result.stdout  # chart name
    assert "v1.12.1" in result.stdout  # image tag


def test_image_list_no_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that image list reports nothing found when there are none."""
    monkeypatch.setattr("stowk8s.commands.image.check_helm_installed", lambda: True)
    fake_result = type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
    monkeypatch.setattr("stowk8s.commands.image.run_dependency_update", lambda *a: fake_result)
    monkeypatch.setattr("stowk8s.commands.image.walk_dependency_tree", lambda *a: [])
    result = runner.invoke(main, ["image", "list", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 0
    assert "No image dependencies found" in result.stdout


def test_oci_url_construction() -> None:
    """Test that OCI URLs include the chart name appended to the repository base."""
    from stowk8s.utils.image_resolver import pull_oci_dependency
    from unittest.mock import patch
    import tempfile
    from pathlib import Path

    dep = {
        "name": "my-chart",
        "version": "1.0.0",
        "repository": "oci://example.com/my-registry/charts",
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "Result", (), {"returncode": 0, "stderr": "", "stdout": ""}
            )()
            # Create the expected directory structure
            (tmp_path / "my-chart-1.0.0").mkdir()
            result = pull_oci_dependency(dep, tmp_path)
            assert result is not None

            # Verify the URL contains the chart name
            call_args = mock_run.call_args
            assert call_args is not None
            cmd = call_args[0][0]
            assert "oci://example.com/my-registry/charts/my-chart" in cmd


def test_annotations_images_parsing() -> None:
    """Test parsing of Bitnami-style annotations.images field."""
    from stowk8s.utils.image_resolver import parse_image_annotations

    chart_data = {
        "name": "test-chart",
        "version": "1.0.0",
        "annotations": {
            "images": """- name: grafana-mimir
  version: 3.0.5
  image: us-east1-docker.pkg.dev/vmw-app-catalog/hosted-registry-f00e7443adc/containers/photon-5/grafana-mimir:3.0.5-photon-5-r2
- name: nginx
  version: 1.30.0
  image: us-east1-docker.pkg.dev/vmw-app-catalog/hosted-registry-f00e7443adc/containers/photon-5/nginx:1.30.0-photon-5-r1
"""
        },
    }

    images = parse_image_annotations(chart_data, "test-chart")
    assert len(images) == 2
    assert images[0].image_name == "grafana-mimir"
    assert images[0].image_tag == "3.0.5"
    assert images[0].sources == ["annotations.images"]
    assert images[1].image_name == "nginx"
    assert images[1].image_tag == "1.30.0"

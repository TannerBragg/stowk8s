"""Tests for the helm command group."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

import pytest
from typer.testing import CliRunner

from stowk8s.cli import main
from stowk8s.utils.image_resolver import ImageDependency

runner = CliRunner()
SAMPLE_CHARTS = Path(__file__).parent.parent / "sample"


def test_helm_dependency_update_no_helm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test helm dependency update fails when helm is missing."""
    monkeypatch.setattr("stowk8s.commands.helm.check_helm_installed", lambda: False)
    result = runner.invoke(main, ["helm", "dependency", "update", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 1
    assert "helm is not installed" in result.stdout


def test_helm_dependency_update_invalid_dir() -> None:
    """Test helm dependency update fails on a non-existent chart directory."""
    result = runner.invoke(main, ["helm", "dependency", "update", "-C", "/nonexistent/path"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_helm_dependency_update_success_no_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test helm dependency update with no image dependencies."""
    fake_result = type("Result", (), {"returncode": 0, "stderr": "", "stdout": "updating dependencies"})()
    monkeypatch.setattr("stowk8s.commands.helm.check_helm_installed", lambda: True)
    monkeypatch.setattr("stowk8s.commands.helm.run_dependency_update", lambda *a: fake_result)
    monkeypatch.setattr("stowk8s.commands.helm.walk_dependency_tree", lambda *a: [])
    result = runner.invoke(main, ["helm", "dependency", "update", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 0
    assert "No image dependencies found" in result.stdout


def test_helm_dependency_update_success_with_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test helm dependency update with image dependencies."""
    fake_result = type("Result", (), {"returncode": 0, "stderr": "", "stdout": "updating dependencies"})()
    monkeypatch.setattr("stowk8s.commands.helm.check_helm_installed", lambda: True)
    monkeypatch.setattr("stowk8s.commands.helm.run_dependency_update", lambda *a: fake_result)
    fake_images = [
        ImageDependency("sample-app", "0.1.0", "nginx", "1.25", "image.name"),
    ]
    monkeypatch.setattr("stowk8s.commands.helm.walk_dependency_tree", lambda *a: fake_images)
    result = runner.invoke(main, ["helm", "dependency", "update", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 0
    assert "Image Dependencies (after dependency update)" in result.stdout
    assert "nginx" in result.stdout


def test_helm_dependency_update_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test helm dependency update handles helm errors."""
    fake_result = type("Result", (), {"returncode": 1, "stderr": "chart not found", "stdout": ""})()
    monkeypatch.setattr("stowk8s.commands.helm.check_helm_installed", lambda: True)
    monkeypatch.setattr("stowk8s.commands.helm.run_dependency_update", lambda *a: fake_result)
    result = runner.invoke(main, ["helm", "dependency", "update", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 1
    assert "helm dependency update failed" in result.stdout

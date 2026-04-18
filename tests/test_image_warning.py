"""Tests for image.py warning path on helm update failure."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from stowk8s.cli import main
from stowk8s.utils.image_resolver import ImageDependency

runner = CliRunner()
SAMPLE_CHARTS = Path(__file__).parent.parent / "sample"


def test_image_list_helm_update_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that image list shows a warning when helm update has issues but proceeds."""
    fake_result = type("Result", (), {"returncode": 1, "stderr": "some helm error", "stdout": ""})()
    monkeypatch.setattr("stowk8s.commands.image.check_helm_installed", lambda: True)
    monkeypatch.setattr("stowk8s.commands.image.run_dependency_update", lambda *a: fake_result)
    fake_images = [ImageDependency("sample-app", "0.1.0", "nginx", "1.25", "image.name")]
    monkeypatch.setattr("stowk8s.commands.image.walk_dependency_tree", lambda *a: fake_images)
    result = runner.invoke(main, ["image", "list", "-C", str(SAMPLE_CHARTS)])
    assert result.exit_code == 0
    assert "helm dependency update had issues" in result.stdout
    assert "some helm error" in result.stdout

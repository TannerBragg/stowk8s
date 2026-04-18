"""Tests for the CLI main entry point."""

from typer.testing import CliRunner

from stowk8s.cli import main
from stowk8s import __version__

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_list() -> None:
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "helm" in result.stdout
    assert "list" in result.stdout
    assert "version" in result.stdout

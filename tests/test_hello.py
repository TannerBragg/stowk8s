"""Tests for the hello command group."""

from typer.testing import CliRunner

from stowk8s.cli import main
from stowk8s.utils.formatter import print_greeting

runner = CliRunner()


def test_hello_simple() -> None:
    result = runner.invoke(main, ["hello", "simple"])
    assert result.exit_code == 0
    assert "Hello, world!" in result.stdout


def test_hello_with_name() -> None:
    result = runner.invoke(main, ["hello", "simple", "-n", "Typer"])
    assert result.exit_code == 0
    assert "Hello, Typer!" in result.stdout


def test_hello_shout() -> None:
    greeting = print_greeting("test", shout=True)
    assert "WORLD" in greeting or "TEST" in greeting


def test_hello_table() -> None:
    result = runner.invoke(main, ["hello", "table"])
    assert result.exit_code == 0
    assert "Hello List" in result.stdout


def test_version() -> None:
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

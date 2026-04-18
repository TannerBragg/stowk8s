"""Tests for the formatter module."""

from stowk8s.utils.formatter import (
    print_greeting,
    print_styled_table,
    print_warning,
    print_error,
)


def test_print_greeting_normal() -> None:
    result = print_greeting("Typer")
    assert "Hello, [bold]Typer![/bold]" in result


def test_print_greeting_shout() -> None:
    result = print_greeting("Typer", shout=True)
    assert "HELLO" in result and "TYPER" in result


def test_print_greeting_shout_returns_upper() -> None:
    result = print_greeting("test", shout=True)
    assert result.isupper()


def test_print_styled_table() -> None:
    # Just verify it doesn't raise
    print_styled_table(
        headers=["A", "B"],
        rows=[("1", "2"), ("3", "4")],
        title="Test Table",
        col_styles=["cyan", "green"],
        row_styles=["dim", ""],
    )


def test_print_warning() -> None:
    # Just verify it doesn't raise
    print_warning("test warning message")


def test_print_error() -> None:
    # Just verify it doesn't raise
    print_error("test error message")

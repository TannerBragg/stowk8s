"""Hello world command group — demonstrates the full scaffold."""

import typer

from stowk8s.utils.formatter import print_greeting, print_styled_table, print_warning, print_error

app = typer.Typer(
    name="hello",
    help="Display greeting messages.",
    rich_markup_mode="rich",
)


@app.command()
def simple(
    name: str = typer.Option("world", "--name", "-n", help="Name to greet."),
    shout: bool = typer.Option(False, "--shout", "-s", help="Shout the greeting."),
) -> None:
    """Print a simple formatted greeting to the terminal."""
    print_greeting(name, shout=shout)


@app.command()
def table(
    names: list[str] = typer.Option(["Alice", "Bob", "Charlie"], help="Names to display."),
) -> None:
    """Display names in a rich-styled table."""
    data = [(i + 1, n, len(n) * "~", "active") for i, n in enumerate(names)]
    print_styled_table(
        headers=["#", "Name", "Tilde-string", "Status"],
        rows=data,
        title="Hello List",
        row_styles=["dim", ""],
    )


@app.command()
def error_demo(
    msg: str = typer.Option("Something went wrong", "--msg", help="Error message to display."),
) -> None:
    """Demonstrate rich error output styling."""
    print_error(msg)


@app.command()
def warning_demo(
    msg: str = typer.Option("This is a warning", "--msg", help="Warning message to display."),
) -> None:
    """Demonstrate rich warning output styling."""
    print_warning(msg)


if __name__ == "__main__":
    app()

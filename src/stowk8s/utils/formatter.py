"""Rich formatting helpers for terminal output."""

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


def print_greeting(name: str, shout: bool = False) -> str:
    """Return and print a styled greeting string.

    Args:
        name: The name to greet.
        shout: If True, display in all caps with an exclamation.

    Returns:
        The formatted greeting string.
    """
    if shout:
        shouted = f"Hello, [bold]{name}![/bold]"
        console.print(Panel(shouted, style="bold green", subtitle="Greeting", subtitle_align="right"))
        return shouted.upper()
    msg = f"Hello, [bold]{name}![/bold]"

    console.print(Rule("[bold]Greeting[/bold]", style="blue"))
    console.print(msg)
    return msg


def print_styled_table(
    headers: list[str],
    rows: list[tuple],
    title: str = "",
    col_styles: list[str] | None = None,
    row_styles: list[str] | None = None,
) -> None:
    """Render a rich-styled table to the terminal.

    Args:
        headers: Column header strings.
        rows: List of row tuples.
        title: Optional table title.
        col_styles: Per-column style strings.
        row_styles: Alternating row style strings.
    """
    table = Table(title=title, title_style="bold cyan", header_style="bold magenta")

    for i, header in enumerate(headers):
        style = col_styles[i] if col_styles else "white"
        table.add_column(header, style=style)

    for row in rows:
        styled_row = []
        for i, cell in enumerate(row):
            style = col_styles[i] if col_styles and i < len(col_styles) else None
            styled_row.append(Text(str(cell), style=style) if style else str(cell))
        table.add_row(*styled_row)

    console.print(table)


def print_error(msg: str) -> None:
    """Display an error message in a red panel."""
    console.print(Panel(f"[bold red]ERROR:[/bold red] {msg}", style="red"))


def print_warning(msg: str) -> None:
    """Display a warning message in a yellow panel."""
    console.print(Panel(f"[bold yellow]WARNING:[/bold yellow] {msg}", style="yellow"))

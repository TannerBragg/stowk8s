"""Main entry point for the stowk8s CLI mainlication."""

import typer

from stowk8s import __version__
from stowk8s.commands import hello, helm, image

main = typer.Typer(
    name="stowk8s",
    help="CLI Application to make helm charts and dependent images portable.",
    add_completion=True,
    rich_markup_mode="rich",
)

main.add_typer(hello.app, name="hello", help="Hello world commands.")
main.add_typer(helm.app, name="helm", help="Work with Helm chart dependencies.")
main.add_typer(image.app, name="image", help="Inspect image dependencies of Helm charts.")


@main.command()
def version(ctx: typer.Context) -> None:
    """Print the installed version."""
    from rich.console import Console

    console = Console()
    console.print(f"stowk8s [bold]{__version__}[/bold]")


@main.callback()
def callback(ctx: typer.Context, quiet: bool = False) -> None:
    """Main callback — all commands share these options."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet


@main.command("list")
def list_commands(ctx: typer.Context) -> None:
    """List all available commands."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Available Commands")
    table.add_column("Group", style="cyan")
    table.add_column("Command", style="green")
    table.add_column("Description", style="white")

    for cmd_name in ["hello", "helm", "list", "version"]:
        table.add_row("stowk8s", cmd_name, f"Run 'stowk8s {cmd_name} --help' for details")

    console.print(table)


if __name__ == "__main__":
    main()

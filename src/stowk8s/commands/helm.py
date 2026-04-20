"""Helm chart dependency management commands."""

import typer
from pathlib import Path

from stowk8s.utils.formatter import print_error, print_styled_table, print_warning
from stowk8s.utils.helm_utils import check_helm_installed, run_dependency_update
from stowk8s.utils.file_ops import find_and_extract_targz
from stowk8s.strategies import StrategyManager
from stowk8s.strategies.base import ImageDependency


app = typer.Typer(
    name="helm",
    help="Work with Helm chart dependencies.",
    rich_markup_mode="rich",
)

dependency = typer.Typer(
    name="dependency",
    help="Manage chart dependencies.",
    rich_markup_mode="rich",
)


def walk_dependency_tree(chart_dir: str | Path) -> list[ImageDependency]:
    """Return image dependencies for the chart directory."""
    return StrategyManager().find_all(Path(chart_dir))


@dependency.command()
def update(
    chart_dir: str = typer.Option(".", "--chart-dir", "-C", help="Path to the Helm chart directory."),
) -> None:
    """Update chart dependencies by pulling latest versions."""
    chart_path = Path(chart_dir).resolve()
    if not chart_path.is_dir():
        print_error(f"Chart directory not found: {chart_path}")
        raise typer.Exit(code=1)

    if not check_helm_installed():
        print_error("helm is not installed or not on PATH.")
        raise typer.Exit(code=1)

    try:
        run_dependency_update(chart_path)
        extracted_dirs = find_and_extract_targz(str(chart_dir))
        print(f"[stowk8s] Extracted {len(extracted_dirs)} chart(s).")
    except Exception as e:
        print(f"[stowk8s] WARNING: helm dependency update or extraction failed: {e}")

app.add_typer(dependency, name="dependency", help="Manage chart dependencies.")
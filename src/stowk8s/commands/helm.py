"""Helm chart dependency management commands."""

import typer

from stowk8s.utils.formatter import print_error, print_styled_table, print_warning
from stowk8s.utils.image_resolver import check_helm_installed, run_dependency_update, walk_dependency_tree

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


@dependency.command()
def update(
    chart_dir: str = typer.Option(".", "--chart-dir", "-C", help="Path to the Helm chart directory."),
) -> None:
    """Update chart dependencies by pulling latest versions."""
    from pathlib import Path

    chart_path = Path(chart_dir).resolve()
    if not chart_path.is_dir():
        print_error(f"Chart directory not found: {chart_path}")
        raise typer.Exit(code=1)

    if not check_helm_installed():
        print_error("helm is not installed or not on PATH.")
        raise typer.Exit(code=1)

    # Run helm dependency update
    result = run_dependency_update(chart_path)

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        print_error(f"helm dependency update failed:\n{stderr}")
        raise typer.Exit(code=1)

    stdout = result.stdout.strip()
    if stdout:
        for line in stdout.splitlines():
            print(f"  {line}")

    # After successful update, show the full image inventory
    images = walk_dependency_tree(chart_path)

    if not images:
        print_warning("No image dependencies found after update.")
        raise typer.Exit(code=0)

    rows = [(img.source_chart, img.source_chart_version, img.image_name, img.image_tag, ", ".join(img.sources)) for img in images]

    print_styled_table(
        headers=["Chart", "Version", "Image", "Tag", "Source"],
        rows=rows,
        title="Image Dependencies (after dependency update)",
    )


app.add_typer(dependency, name="dependency", help="Manage chart dependencies.")

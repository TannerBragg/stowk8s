"""Image list command group -- list all image dependencies from Helm charts."""

import typer

from stowk8s.utils.formatter import print_error, print_styled_table, print_warning
from stowk8s.utils.image_resolver import check_helm_installed, walk_dependency_tree

app = typer.Typer(
    name="image",
    help="Inspect image dependencies of Helm charts.",
    rich_markup_mode="rich",
)


@app.command()
def list(
    chart_dir: str = typer.Option(".", "--chart-dir", "-C", help="Path to the Helm chart directory."),
) -> None:
    """List all image dependencies from a Helm chart's dependency tree."""
    from pathlib import Path

    chart_path = Path(chart_dir).resolve()
    if not chart_path.is_dir():
        print_error(f"Chart directory not found: {chart_path}")
        raise typer.Exit(code=1)

    if not check_helm_installed():
        print_error("helm is not installed or not on PATH.")
        raise typer.Exit(code=1)

    images = walk_dependency_tree(chart_path)

    if not images:
        print_warning("No image dependencies found.")
        raise typer.Exit(code=0)

    rows = [(img.source_chart, img.source_chart_version, img.image_name, img.image_tag, ", ".join(img.sources), img.full_reference) for img in images]

    print_styled_table(
        headers=["Chart", "Version", "Image", "Tag", "Source", "Image Reference"],
        rows=rows,
        title="Image Dependencies",
    )

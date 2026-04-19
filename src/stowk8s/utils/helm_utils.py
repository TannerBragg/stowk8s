"""Helm-related utility functions."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def check_helm_installed() -> bool:
    """Check if helm is available on PATH."""
    return shutil.which("helm") is not None


def run_dependency_update(chart_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run helm dependency update against a chart directory.

    Args:
        chart_dir: Path to the Helm chart directory.

    Returns:
        CompletedProcess result from the subprocess call.
    """
    return subprocess.run(
        ["helm", "dependency", "update", str(chart_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )

"""File operations for Helm chart dependency management."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Any

def extract_targz(targz_path: str | Path) -> None:
    """Extract a .tar.gz archive into its own directory.

    The archive is extracted to the same directory as the archive file.
    """
    path = Path(targz_path)
    if not path.is_file():
        raise FileNotFoundError(f"Targz file not found: {path}")
    archive_dir = path.parent
    with tarfile.open(path, "r:gz") as tar:
        tar.extractall(archive_dir)

def find_and_extract_targz(search_path: str | Path) -> list[Path]:
    """Find all .tgz files in search_path and extract them.

    Returns a list of the directories each archive was extracted to.
    """
    base = Path(search_path)
    if not base.exists():
        raise FileNotFoundError(f"Path not found: {base}")
    if base.is_file():
        base = base.parent
    # Recursively find .tgz files
    matches = list(base.glob("**/*.tgz"))
    extracted_dirs: list[Path] = []
    for tgz in matches:
        try:
            extract_targz(tgz)
            extracted_dirs.append(tgz.parent)
        except Exception as e:
            print(f"[stowk8s] WARNING: failed to extract {tgz}: {e}")
    return extracted_dirs

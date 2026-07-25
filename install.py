#!/usr/bin/env python3
"""Friendly entry point for the selectable AI Skills installer."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "scripts" / "setup.py"),
        run_name="__main__",
    )

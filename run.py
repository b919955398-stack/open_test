#!/usr/bin/env python
"""Repository-local entry point; safe to run without installing the package."""

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from psse_open.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

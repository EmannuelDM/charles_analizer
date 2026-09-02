#!/usr/bin/env python3
"""
Main script to analyze Charles Proxy files.
Example usage script targeting example_1.chlz.
"""

import sys
from pathlib import Path

pkg_dir = Path(__file__).resolve().parent
parent_dir = pkg_dir.parent

if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

try:
    from charles_analizer.cli import main
except ImportError:
    from cli import main

if __name__ == "__main__":
    main()

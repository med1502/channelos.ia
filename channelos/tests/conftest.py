"""
Pytest configuration — shared fixtures for ChannelOS tests.
"""
import sys
import os
from pathlib import Path

# Ensure the project root is on sys.path so `channelos` is importable
# even without `pip install -e .`
ROOT = Path(__file__).parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

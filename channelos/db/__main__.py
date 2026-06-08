"""
Entry point for: python3 -m channelos.db [init|costs]
Using the package invocation avoids the runpy RuntimeWarning
that occurs with: python3 -m channelos.db.client
"""
import sys
from channelos.db.client import cli

if __name__ == "__main__":
    cli()
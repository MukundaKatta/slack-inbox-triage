"""Test package for slack-inbox-triage.

This makes the ``src`` layout importable when the suite is run with the
standard-library test runner::

    python3 -m unittest discover -s tests

so the tests have no third-party dependency (no pytest required).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

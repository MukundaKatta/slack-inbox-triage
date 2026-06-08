"""Make the ``src`` layout importable for the standard-library test runner.

When the suite is run with::

    python3 -m unittest discover -s tests

unittest puts the ``tests`` directory on ``sys.path`` and imports each
test module by its base name, so the package ``__init__`` does not run.
Every test module imports this module first so the ``slack_inbox_triage``
package under ``src`` is importable without installing anything and without
any third-party test dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

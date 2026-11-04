"""Pytest discovery glue.

Adds `<repo>/backend` and `<repo>` to `sys.path` so `import sql_safety`,
`import routes.ask` and `from backend.routes import ...` all work from
anywhere without requiring the user to export PYTHONPATH — both under
`python -m pytest` and the plain `pytest` console script (what CI runs),
which do not put the same directories on the path. The runtime has the
same trick in `backend/main.py` (for the import of `db`/`routes`) — we
mirror it here so the test suite has parity.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

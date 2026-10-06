"""Make `src` importable when a script is run as `python scripts/<name>.py`.

`pip install -e .` makes this unnecessary; it keeps the documented
commands working on a plain clone too.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is in requirements.txt; tolerate its absence
    pass
else:
    load_dotenv(ROOT / ".env")

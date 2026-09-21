"""Vercel Python runtime entrypoint: every path is rewritten here (vercel.json) and served by ChartHandler."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import ChartHandler  # noqa: E402


class handler(ChartHandler):
    pass

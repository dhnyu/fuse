import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / "python")
if PYTHON not in sys.path:
    sys.path.insert(0, PYTHON)

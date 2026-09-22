"""
CLI: force re-index toan bo data/raw/ vao ChromaDB (xoa index cu, build lai tu dau).

Cach dung:
    python scripts/chunk_and_index.py

Logic chinh nam o backend/indexer.py (dung chung voi backend/app.py, noi tu
dong rebuild index khi khoi dong neu Chroma dang rong).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.indexer import build_index

if __name__ == "__main__":
    build_index()

"""
Logic dung chung: doc file .txt da crawl trong data/raw/, chia nho (chunk),
tao embedding bang OpenAI, va luu vao ChromaDB (persist local).

Duoc goi boi scripts/chunk_and_index.py (CLI, force re-index) va
backend/app.py (tu dong rebuild khi khoi dong neu Chroma dang rong - can
thiet cho moi truong deploy free-tier khong co persistent disk).
"""

import re
from pathlib import Path

import chromadb
import openai

from backend import config

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

CHUNK_SIZE_CHARS = 1200       # ~ vai tram token, du de giu ngu canh 1 dieu/khoan
CHUNK_OVERLAP_CHARS = 200     # tranh cat dut y giua 2 chunk lien tiep
EMBED_BATCH_SIZE = 64


def parse_raw_file(path: Path) -> tuple[str, str, str]:
    """Tra ve (source_url, title, body) tu file da crawl."""
    raw = path.read_text(encoding="utf-8")
    header, _, body = raw.partition("\n---\n")
    source_url = ""
    title = ""
    for line in header.splitlines():
        if line.startswith("SOURCE_URL:"):
            source_url = line.removeprefix("SOURCE_URL:").strip()
        elif line.startswith("TITLE:"):
            title = line.removeprefix("TITLE:").strip()
    return source_url, title, body.strip()


def chunk_text(text: str, size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Chia van ban theo doan (paragraph), gop lai thanh chunk ~size ky tu,
    co overlap de khong mat ngu canh o ranh gioi chunk."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= size:
            current = f"{current}\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # bat dau chunk moi, giu lai phan overlap tu cuoi chunk truoc
            tail = current[-overlap:] if current else ""
            current = f"{tail}\n{para}".strip()
    if current:
        chunks.append(current)

    # Neu 1 doan don le da vuot qua size (vd van ban khong xuong dong), cat cung theo ky tu
    final_chunks = []
    for c in chunks:
        if len(c) <= size * 1.5:
            final_chunks.append(c)
        else:
            for i in range(0, len(c), size - overlap):
                final_chunks.append(c[i:i + size])
    return final_chunks


def embed_texts(client: openai.OpenAI, texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        result = client.embeddings.create(input=batch, model=config.OPENAI_EMBED_MODEL)
        embeddings.extend(item.embedding for item in result.data)
    return embeddings


def build_index() -> int:
    """Xoa collection cu (neu co) va index lai toan bo tu dau. Tra ve so chunk da luu."""
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.txt")):
        print(f"Khong tim thay file .txt nao trong {RAW_DIR}. Hay chay scripts/crawl.py truoc.")
        return 0

    openai_client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    chroma_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)

    try:
        chroma_client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:
        pass
    collection = chroma_client.create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks: list[str] = []
    all_metadatas: list[dict] = []
    all_ids: list[str] = []

    for path in sorted(RAW_DIR.glob("*.txt")):
        source_url, title, body = parse_raw_file(path)
        if not body:
            continue
        chunks = chunk_text(body)
        for idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({
                "source_url": source_url,
                "title": title,
                "file": path.name,
                "chunk_index": idx,
            })
            all_ids.append(f"{path.stem}_{idx}")
        print(f"{path.name}: {len(chunks)} chunk")

    if not all_chunks:
        return 0

    print(f"\nTong so chunk: {len(all_chunks)}. Dang tao embedding qua OpenAI ({config.OPENAI_EMBED_MODEL})...")
    embeddings = embed_texts(openai_client, all_chunks)

    collection.add(
        ids=all_ids,
        embeddings=embeddings,
        documents=all_chunks,
        metadatas=all_metadatas,
    )

    print(f"Da luu {len(all_chunks)} chunk vao ChromaDB tai '{config.CHROMA_PERSIST_DIR}' (collection '{config.CHROMA_COLLECTION}').")
    return len(all_chunks)


def ensure_index() -> None:
    """Goi khi backend khoi dong: neu collection chua ton tai hoac dang rong,
    tu dong build tu data/raw/ da commit san trong repo. Can thiet cho host
    free-tier khong co persistent disk (data/chroma bi xoa moi lan deploy)."""
    chroma_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        collection = chroma_client.get_collection(config.CHROMA_COLLECTION)
        if collection.count() > 0:
            return
    except Exception:
        pass

    print("ChromaDB dang rong - tu dong build index tu data/raw/ ...")
    build_index()

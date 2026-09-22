"""
Crawl noi dung noi quy / quy che tu cac trang web cua truong.

Cach dung:
    python scripts/crawl.py

Doc URL tu scripts/seed_urls.txt (moi dong 1 URL, dong bat dau bang # bi bo qua),
tai trang, trich xuat noi dung van ban chinh (bo header/footer/menu), va luu thanh
file .txt trong data/raw/ (1 file / URL) kem metadata (nguon, tieu de) o dong dau file.

Luu y:
- Chi crawl cac trang ban co quyen/duoc phep thu thap du lieu (public, khong bi robots.txt chan).
- Script nay KHONG tu dong follow link noi bo (tranh crawl lan man ngoai y muon).
  Neu muon crawl theo do sau, tu bo sung logic BFS trong ham `crawl_seed_urls`.
"""

import io
import re
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

SEED_FILE = Path(__file__).parent / "seed_urls.txt"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw"
REQUEST_DELAY_SECONDS = 1.5  # lich su voi server cua truong, tranh spam request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HUST-NoiQuy-RAG-Bot/1.0; +educational-project)"
}

# Cac the HTML thuong chua noi dung "rac" can loai bo truoc khi trich xuat text
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]


def load_seed_urls() -> list[str]:
    if not SEED_FILE.exists():
        raise FileNotFoundError(f"Khong tim thay {SEED_FILE}")
    urls = []
    for line in SEED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def extract_main_text(html: str) -> tuple[str, str]:
    """Tra ve (tieu_de, noi_dung_van_ban) da lam sach tu HTML tho."""
    soup = BeautifulSoup(html, "lxml")

    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Khong ro tieu de"

    # Uu tien noi dung trong cac khoi <article> / <main> / div co class chua "content"
    main_candidates = soup.find_all(["article", "main"])
    main_candidates += soup.find_all("div", class_=re.compile(r"content|noidung|article|post", re.I))

    container = main_candidates[0] if main_candidates else soup.body or soup

    text = container.get_text(separator="\n", strip=True)
    # Gop cac dong trong lien tiep
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text


def extract_pdf_text(content: bytes) -> tuple[str, str]:
    """Tra ve (tieu_de, noi_dung_van_ban) tu noi dung file PDF (bytes)."""
    reader = PdfReader(io.BytesIO(content))

    title = ""
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title.strip()

    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(pages_text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if not title:
        # dung dong dau tien khong rong lam tieu de tam
        for line in text.splitlines():
            if line.strip():
                title = line.strip()[:150]
                break
    return title or "Khong ro tieu de", text


def is_pdf_response(url: str, resp: requests.Response) -> bool:
    content_type = resp.headers.get("Content-Type", "")
    return url.lower().endswith(".pdf") or "application/pdf" in content_type.lower()


def safe_filename(url: str) -> str:
    parsed = urlparse(url)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", parsed.path).strip("-") or "index"
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{parsed.netloc}_{slug}_{url_hash}.txt"


def crawl_seed_urls() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = load_seed_urls()

    if not urls:
        print(
            "scripts/seed_urls.txt chua co URL nao (chi co dong comment vi du). "
            "Hay them URL that cua nha truong roi chay lai."
        )
        return

    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{len(urls)}] Dang tai: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Loi khi tai {url}: {e}")
            continue

        if is_pdf_response(url, resp):
            try:
                title, text = extract_pdf_text(resp.content)
            except Exception as e:
                print(f"  Loi khi doc PDF {url}: {e}")
                continue
        else:
            title, text = extract_main_text(resp.text)
        if len(text) < 200:
            print(f"  Canh bao: noi dung trich xuat qua ngan ({len(text)} ky tu), kiem tra lai selector.")

        out_path = OUTPUT_DIR / safe_filename(url)
        out_path.write_text(
            f"SOURCE_URL: {url}\nTITLE: {title}\n---\n{text}",
            encoding="utf-8",
        )
        print(f"  Da luu: {out_path.name} ({len(text)} ky tu)")

        time.sleep(REQUEST_DELAY_SECONDS)

    print("\nHoan tat crawl. Kiem tra thu muc data/raw/ va doc lai noi dung truoc khi index.")


if __name__ == "__main__":
    crawl_seed_urls()

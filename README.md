# Trợ lý Nội quy HUST (RAG Chatbot)

Chatbot hỏi-đáp về nội quy/quy chế Đại học Bách khoa Hà Nội, dùng kiến trúc RAG
(Retrieval-Augmented Generation): tài liệu thật của trường được index vào vector
database, mỗi câu hỏi sẽ truy hồi đoạn văn bản liên quan rồi đưa vào Claude làm
ngữ cảnh để trả lời — hạn chế bịa đặt và có trích dẫn nguồn.

## Kiến trúc

```
scripts/crawl.py           -> tải nội dung nội quy từ website trường (data/raw/*.txt)
scripts/chunk_and_index.py -> chia nhỏ văn bản, tạo embedding (OpenAI), lưu vào ChromaDB (data/chroma/)
backend/app.py              -> FastAPI: nhận câu hỏi, truy hồi (RAG), gọi Claude API, trả lời + nguồn
frontend/                   -> giao diện chat HTML/CSS/JS thuần, gọi backend qua /api/chat
```

## Chuẩn bị

1. Python 3.10+
2. Tạo virtualenv và cài dependency:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Copy `.env.example` thành `.env` và điền API key:

   ```powershell
   copy .env.example .env
   ```

   - `ANTHROPIC_API_KEY`: lấy tại https://console.anthropic.com/ (dùng để gọi
     Claude sinh câu trả lời)
   - `OPENAI_API_KEY`: lấy tại https://platform.openai.com/api-keys (dùng để
     tạo embedding qua `text-embedding-3-small` — Claude API không có
     embedding model riêng nên cần dùng bên thứ ba)

## Bước 1 — Thu thập dữ liệu nội quy

`scripts/seed_urls.txt` đã có sẵn một số URL chính thức từ hust.edu.vn tìm được
qua web search ngày 2026-09-22 (Quy chế đào tạo 2025, Quy chế công tác sinh
viên 2025, đánh giá kết quả rèn luyện...). Phần lớn là file PDF — `crawl.py`
đã hỗ trợ trích xuất text từ cả PDF lẫn trang HTML thường.

**Trước khi chạy, bạn vẫn cần:**
- Mở từng URL, xác nhận văn bản còn hiệu lực (quy chế có thể được cập nhật
  theo năm học).
- Bổ sung các mục còn thiếu: nội quy ký túc xá, quy định học phí/học bổng —
  xem phần TODO ở cuối file `seed_urls.txt`.

```powershell
python scripts/crawl.py
```

Kết quả lưu vào `data/raw/*.txt`. Nên đọc lại vài file để chắc chắn nội dung
trích xuất đúng (không lẫn menu, quảng cáo...).

> Nếu trang web dùng JavaScript để render nội dung (crawl bằng `requests` ra
> trang trống), cần thay bằng công cụ crawl hỗ trợ JS (Playwright/Selenium) -
> báo mình nếu gặp trường hợp này để bổ sung.

## Bước 2 — Index vào vector database

```powershell
python scripts/chunk_and_index.py
```

Script sẽ chia văn bản thành các đoạn ~1200 ký tự (có overlap), tạo embedding
qua OpenAI (`text-embedding-3-small`), và lưu vào ChromaDB tại `data/chroma/`.

## Bước 3 — Chạy backend

```powershell
uvicorn backend.app:app --reload --port 8000
```

Mở trình duyệt tại `http://localhost:8000` — FastAPI phục vụ luôn cả giao diện
chat tĩnh trong `frontend/`.

## Đánh giá chất lượng RAG

```powershell
python scripts/eval_rag.py
```

Chạy bộ câu hỏi mẫu (đáp án đối chiếu trực tiếp từ `data/raw/`) qua toàn bộ
pipeline, dùng Claude làm giám khảo (LLM-as-judge) chấm 5 metric: chi tiết ở
docstring đầu file. Hữu ích để phát hiện các trường hợp retrieval bỏ sót thông
tin dù dữ liệu đã có trong index (context_recall thấp) — khác với trường hợp
dữ liệu thực sự chưa được crawl. Nên bổ sung thêm câu hỏi vào `EVAL_SET` khi
crawl thêm nguồn mới hoặc đổi tham số chunking/embedding, để so sánh trước/sau.

## Cấu hình chi phí / chất lượng

Trong `.env`:

- `CLAUDE_MODEL`: mặc định `claude-opus-5` (chất lượng cao nhất). Với chatbot
  FAQ khối lượng lớn, có thể đổi sang `claude-sonnet-5` (rẻ hơn ~2.5 lần) mà
  vẫn đủ tốt cho hầu hết câu hỏi nội quy.
- `RAG_TOP_K`: số đoạn văn bản truy hồi cho mỗi câu hỏi (mặc định 5).

## Deploy public (Render.com, free tier)

Kiến trúc đã được chuẩn bị để deploy lên host free-tier không có persistent
disk: `data/raw/*.txt` (văn bản đã crawl) được commit vào repo, và
`backend/app.py` tự động rebuild ChromaDB từ đó ngay khi khởi động nếu phát
hiện index đang rỗng (xem `backend/indexer.py::ensure_index`). Vì vậy không
cần chạy `crawl.py`/`chunk_and_index.py` thủ công trên server.

**Bước 1 — Đẩy code lên GitHub**

```powershell
git init
git add .
git commit -m "Initial commit"
```

Tạo repo mới trên GitHub rồi push lên (thay `<your-repo-url>`):

```powershell
git remote add origin <your-repo-url>
git branch -M main
git push -u origin main
```

⚠️ Kiểm tra `git status` trước khi commit để chắc chắn file `.env` (chứa API
key thật) không bị add nhầm — file này đã có trong `.gitignore`.

**Bước 2 — Tạo Web Service trên Render**

1. Đăng ký/đăng nhập tại https://render.com, chọn **New > Web Service**, kết
   nối với repo GitHub vừa tạo.
2. Cấu hình:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
3. Thêm **Environment Variables** (tab Environment) — copy từ `.env` của bạn,
   **không** copy `CHROMA_PERSIST_DIR`/`CHROMA_COLLECTION` nếu muốn giữ mặc
   định:
   - `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`
   - `OPENAI_API_KEY`, `OPENAI_EMBED_MODEL`
   - `RAG_TOP_K`, `RATE_LIMIT_PER_MINUTE`
   - `ALLOWED_ORIGINS` — để tạm `*` cho lần deploy đầu, sau khi có domain thật
     (vd `https://ten-app.onrender.com`) thì sửa lại thành domain đó và deploy
     lại để siết CORS.
4. Bấm **Create Web Service**. Lần build đầu sẽ mất vài phút (cài dependency +
   tự động tạo embedding cho ~270 chunk khi khởi động lần đầu).

**Lưu ý free tier:**
- Service sẽ "ngủ" sau ~15 phút không có traffic; lần truy cập đầu tiên sau đó
  chậm hơn (server phải khởi động lại + rebuild index, có thể mất 30-60s).
- Không có persistent disk: `data/chroma/` bị xóa mỗi lần deploy/restart,
  nhưng sẽ tự rebuild lại từ `data/raw/*.txt` đã commit — không mất dữ liệu,
  chỉ tốn thời gian chờ ở lần đầu.
- Đã có rate limit (`RATE_LIMIT_PER_MINUTE`, mặc định 8 request/phút/IP) để
  hạn chế bị lạm dụng gây tốn phí Anthropic/OpenAI — có thể tăng/giảm tùy nhu
  cầu thực tế.

## Việc cần làm tiếp theo (gợi ý)

- Xác minh và điền danh sách URL nguồn nội quy chính thức vào `scripts/seed_urls.txt`.
- Thêm cơ chế re-index định kỳ (nội quy có thể cập nhật theo năm học) — hiện
  tại cần chạy lại `chunk_and_index.py` thủ công rồi commit `data/raw/` mới.
- Nếu traffic thật tăng cao, cân nhắc nâng cấp Render lên gói trả phí (không
  bị sleep) hoặc chuyển rate limit sang store dùng chung (Redis) nếu scale
  nhiều instance.
- Cân nhắc thêm bộ lọc/logging để theo dõi các câu hỏi mà bot không trả lời
  được (không tìm thấy ngữ cảnh phù hợp) — đây thường là tín hiệu tốt để biết
  cần crawl thêm nguồn nào.

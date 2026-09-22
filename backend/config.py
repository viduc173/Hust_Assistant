import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "hust_noiquy")

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Danh sach domain duoc phep goi API (phan cach boi dau phay). Mac dinh "*" de
# de test - khi da co domain public that, sua ALLOWED_ORIGINS trong .env thanh
# domain cu the (vd https://ten-app.onrender.com) de sat CORS lai.
_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    ["*"] if _allowed_origins_raw.strip() == "*"
    else [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]
)

# So request toi da / IP / phut cho endpoint /api/chat - chong lam dung API tra phi.
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "8"))

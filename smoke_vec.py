import sys
sys.path.insert(0, "src")
from fastapi.testclient import TestClient
from threadline.config import Settings
from threadline.main import create_app
import os
os.makedirs("./data", exist_ok=True)
s = Settings(THREADLINE_ENV="test", DATABASE_URL="sqlite:///./data/vect.db", VECTOR_ENABLED=True, VECTOR_BACKEND="memory", EMBEDDING_BACKEND="hash")
c = TestClient(create_app(s))
c.__enter__()
c.post("/api/v1/documents", files={"file": ("faq.txt", b"password reset guide", "text/plain")})
c.post("/api/v1/documents", files={"file": ("runbook.txt", b"server restart procedure", "text/plain")})
for mode in ["keyword","vector","hybrid"]:
    r = c.get("/api/v1/search", params={"q": "password reset", "mode": mode})
    print(mode, r.status_code, r.json()["total"])
    if r.json()["results"]:
        item=r.json()["results"][0]
        print(" type", item["search_type"], "score", item["score"], "kw", item["keyword_score"], "sem", item["semantic_score"])
c.__exit__(None,None,None)

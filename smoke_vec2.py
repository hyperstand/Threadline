import sys
sys.path.insert(0, "src")
from fastapi.testclient import TestClient
from threadline.config import Settings
from threadline.main import create_app
import os

s = Settings(THREADLINE_ENV="test", DATABASE_URL="sqlite:///./data/v2.db", VECTOR_ENABLED=True, VECTOR_BACKEND="memory", EMBEDDING_BACKEND="hash")
os.makedirs("./data", exist_ok=True)
c = TestClient(create_app(s))
c.__enter__()
r = c.post("/api/v1/documents", files={"file": ("faq.txt", b"password reset guide", "text/plain")})
print("upload", r.status_code)
r2 = c.get("/api/v1/search", params={"q": "password"})
print("search password", r2.status_code, r2.json()["total"])
r3 = c.get("/api/v1/search", params={"q": "password reset"})
print("search phrase", r3.status_code, r3.json()["total"])
c.__exit__(None, None, None)

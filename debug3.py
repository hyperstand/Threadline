import sys
sys.path.insert(0, "src")
from threadline.config import Settings
from threadline.persistence.database import init_storage, create_session_factory
from threadline.ingestion.pipeline import ingest_document

db = "sqlite:///./data/v3.db"
settings = Settings(THREADLINE_ENV="test", DATABASE_URL=db)
init_storage(settings)
engine, sf = create_session_factory(settings)
with sf() as sess:
    d = ingest_document(filename="a.txt", data=b"password reset guide", session=sess, vector_adapter=None, embedding_provider=None)
    print("status", d.status)
    print("chunks", len(d.chunks))
# reopen
with sf() as sess:
    print("reopen chunks", sess.execute(__import__("sqlalchemy").text("SELECT count(*) FROM document_chunks")).scalar())

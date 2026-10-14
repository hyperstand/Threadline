import sys
sys.path.insert(0, "src")
# Import same modules
from threadline.config import Settings
from threadline.memory.manager import MemoryManager
from threadline.integrations.goose import FakeGooseAdapter
from threadline.memory.checkpoint import CheckpointManager
from threadline.persistence.database import init_storage, create_session_factory
import os
os.makedirs("./data", exist_ok=True)
settings = Settings(THREADLINE_ENV="test", DATABASE_URL="sqlite:///./data/m6.db")
init_storage(settings)
engine, sf = create_session_factory(settings)
mm = MemoryManager(settings=settings, session_factory=sf)
cm = CheckpointManager(settings=settings)
from threadline.orchestration.graph import build_investigation_graph
graph = build_investigation_graph(settings=settings, checkpoint_manager=cm, memory_manager=mm, goose_adapter=FakeGooseAdapter())
print("graph channels:", getattr(graph, "channels", None))
print("nodes:", list(graph.nodes))
# invoke minimal
res = graph.invoke({"investigation_id": "x", "question": "q", "target_system": "s", "target_environment": "e", "status": "queued"}, {"configurable": {"thread_id": "t4"}})
print("res keys", sorted(res.keys()))

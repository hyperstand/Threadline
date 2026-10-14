import sys
sys.path.insert(0, "src")
from threadline.memory.checkpoint import CheckpointManager
from threadline.memory.models import WorkingState
cm = CheckpointManager(settings=None, database_url="sqlite:///./data/m6.db")
print("available", cm.available, getattr(cm, "_error", None))
cm.save("inv-1", {"investigation_id": "inv-1", "status": "running", "plan": ["a"]})
print("load after", cm.load("inv-1"))
snap = cm._graph.get_state({"configurable": {"thread_id": "inv-1"}})
print("snapshot values", snap.values)

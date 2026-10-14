from pathlib import Path

from threadline.config import Settings
from threadline.integrations.goose import FakeGooseAdapter
from threadline.memory.checkpoint import CheckpointManager
from threadline.memory.manager import MemoryManager
from threadline.orchestration.graph import build_investigation_graph, run_investigation
from threadline.persistence.database import create_session_factory


def test_m6_graph_live(tmp_path: Path) -> None:
    settings = Settings(threadline_env="dev", threadline_data_dir=str(tmp_path / "data"))
    _, sf = create_session_factory(settings)
    cm = CheckpointManager(settings)
    mm = MemoryManager(settings=settings, session_factory=sf, vector_adapter=None, embedding_provider=None, checkpoint_manager=cm)
    graph = build_investigation_graph(settings=settings, checkpoint_manager=cm, memory_manager=mm, goose_adapter=FakeGooseAdapter())
    result = run_investigation(
        graph,
        investigation_id="inv-graph-1",
        question="why is postgres slow?",
        target_system="postgres",
        target_environment="dev",
    )
    assert result["status"] == "completed"
    assert result["live_evidence"]
    assert result["report"]["summary"]


def test_m6_graph_instance(tmp_path: Path):
    settings = Settings(threadline_env="dev", threadline_data_dir=str(tmp_path / "data"))
    _, sf = create_session_factory(settings)
    cm = CheckpointManager(settings)
    mm = MemoryManager(settings=settings, session_factory=sf, vector_adapter=None, embedding_provider=None, checkpoint_manager=cm)
    graph = build_investigation_graph(settings=settings, checkpoint_manager=cm, memory_manager=mm, goose_adapter=FakeGooseAdapter())
    assert graph is not None

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from threadline.config import Settings
from threadline.integrations.goose import RealGooseAdapter, create_goose_adapter


SHIM = textwrap.dedent(
    """
    import json, sys
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        request = json.loads(line)
        if request.get("method") == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}), flush=True)
        elif request.get("method") == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": [{"name": "get_service_status"}]}}), flush=True)
        elif request.get("method") == "tools/call":
            args = request["params"]["arguments"]
            result_text = json.dumps({"health": "green", "system": args["target_system"]})
            response = {"jsonrpc": "2.0", "id": request["id"], "result": {"content": [{"type": "text", "text": result_text}]}}
            print(json.dumps(response), flush=True)
"""
)


@pytest.fixture
def goose_shim(tmp_path: Path) -> Path:
    path = tmp_path / "goose_shim.py"
    path.write_text(SHIM)
    return path


def test_real_goose_adapter_reads_status(goose_shim: Path) -> None:
    adapter = RealGooseAdapter(command=[sys.executable, str(goose_shim)], timeout_seconds=5, max_output_bytes=65536)
    assert adapter.is_available()
    result = adapter.invoke("get_service_status", target_system="postgres", target_environment="dev")
    assert result["adapter"] == "goose-mcp"
    assert result["result"]["health"] == "green"


def test_real_goose_adapter_rejects_unapproved_tool(goose_shim: Path) -> None:
    from threadline.integrations.goose import GooseToolPolicy

    adapter = RealGooseAdapter(command=[sys.executable, str(goose_shim)], policy=GooseToolPolicy(["get_service_status"]))
    with pytest.raises(ValueError, match="Unapproved"):
        adapter.invoke("drop_data", target_system="postgres", target_environment="dev")


def test_create_goose_adapter_falls_back_when_unavailable(tmp_path: Path) -> None:
    settings = Settings(threadline_env="dev", threadline_data_dir=str(tmp_path / "data"), goose_enabled=True, goose_command="definitely-not-a-goose")
    assert create_goose_adapter(settings) is None

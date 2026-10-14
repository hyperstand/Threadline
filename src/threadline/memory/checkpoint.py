"""LangGraph checkpoint support for M5 working memory."""

from __future__ import annotations

import importlib
import os
import re
import sqlite3
from typing import Any

from threadline.config import Settings
from threadline.redact import redact_secrets

GRAPH_THREAD_PREFIX = "threadline"


def _sqlite_path_from_url(url: str) -> str | None:
    if not url.startswith("sqlite"):
        return None
    remainder = url.split("sqlite:", 1)[1]
    path = remainder.lstrip("/").split("?", 1)[0]
    if url.startswith("sqlite:////"):
        path = "/" + path
    if path in ("", ":memory:", "memory"):
        return None
    return path


class CheckpointManager:
    def __init__(self, settings: Settings | None = None, database_url: str | None = None):
        url = database_url or (settings.database_url if settings is not None else "sqlite:///./data/threadline.db")
        path = _sqlite_path_from_url(url or "")
        self._available = False
        self._graph = None
        self._saver = None
        if path is None:
            return
        try:
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            saver_cls = _import_sqlite_saver()
            self._saver = saver_cls(self._conn)
            from langgraph.graph import StateGraph, START, END

            graph = StateGraph(dict)

            def persist(state: dict[str, Any]) -> dict[str, Any]:
                # Return the supplied state so LangGraph persists it as a checkpoint.
                return dict(state)

            graph.add_node("persist", persist)
            graph.add_edge(START, "persist")
            graph.add_edge("persist", END)
            self._graph = graph.compile(checkpointer=self._saver)
            self._available = True
        except Exception as exc:
            self._available = False
            self._graph = None
            self._saver = None
            self._error = f"{type(exc).__name__}: {redact_secrets(str(exc))}"

    @property
    def available(self) -> bool:
        return self._available

    def save(self, investigation_id: str, state: dict[str, Any]) -> bool:
        if not self._available or self._graph is None:
            return False
        try:
            config = {"configurable": {"thread_id": investigation_id}}
            self._graph.invoke(_safe_state(state), config)
            return True
        except Exception as exc:
            self._error = f"save failed: {type(exc).__name__}: {redact_secrets(str(exc))}"
            return False

    def load(self, investigation_id: str) -> dict[str, Any] | None:
        if not self._available or self._graph is None:
            return None
        try:
            config = {"configurable": {"thread_id": investigation_id}}
            snapshot = self._graph.get_state(config)
            values = getattr(snapshot, "values", None)
            if isinstance(values, dict):
                return values
            return None
        except Exception:
            return None


def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
    # Keep only bounded, reference-sized state in the checkpoint.
    payload: dict[str, Any] = {}
    for key in (
        "investigation_id",
        "question",
        "target_system",
        "target_environment",
        "plan",
        "evidence_ids",
        "hypotheses",
        "completed_steps",
        "pending_checks",
        "iteration_count",
        "tool_call_count",
        "status",
        "run_id",
    ):
        if key in state:
            payload[key] = state[key]
    # Redact possible secret-looking string fields if encountered.
    if "question" in payload and isinstance(payload["question"], str):
        payload["question"] = redact_secrets(payload["question"])
    return payload


def _import_sqlite_saver():
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver

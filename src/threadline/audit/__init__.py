"""Separate audit/trace persistence for Threadline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from threadline.persistence.models import AuditEventModel
from threadline.redact import redact_secrets

logger = logging.getLogger("threadline.audit")


def record_event(
    manager: Any,
    investigation_id: str | None,
    event_type: str,
    *,
    status: str = "completed",
    **safe_metadata: Any,
) -> None:
    """Write one audit event if an audit manager is configured.

    Best-effort: a failed audit write is logged (exception type only) and never
    raised into the investigation workflow.
    """
    if manager is None:
        return
    try:
        manager.record(
            investigation_id,
            event_type,
            status=status,
            safe_metadata=safe_metadata,
            correlation_id=investigation_id,
        )
    except Exception as exc:
        logger.error("audit write failed event_type=%s error=%s", event_type, type(exc).__name__)


class AuditManager:
    def __init__(self, session_factory: Any):
        if isinstance(session_factory, tuple):
            _, session_factory = session_factory
        self._session_factory = session_factory

    def _redact_metadata(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_secrets(value)
        if isinstance(value, dict):
            return {key: self._redact_metadata(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact_metadata(item) for item in value]
        return value

    def record(
        self,
        investigation_id: str | None,
        event_type: str,
        *,
        status: str = "completed",
        actor_type: str = "system",
        actor_id: str | None = None,
        safe_metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        metadata = self._redact_metadata(safe_metadata or {})
        with self._session_factory() as session:
            session.add(
                AuditEventModel(
                    investigation_id=investigation_id,
                    event_type=event_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    timestamp=datetime.now(timezone.utc),
                    status=status,
                    safe_metadata=metadata,
                    correlation_id=correlation_id,
                )
            )
            session.commit()

    def list_events(self, investigation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = (
                session.query(AuditEventModel)
                .filter(AuditEventModel.investigation_id == investigation_id)
                .order_by(AuditEventModel.timestamp)
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": row.id,
                    "investigation_id": row.investigation_id,
                    "event_type": row.event_type,
                    "actor_type": row.actor_type,
                    "actor_id": row.actor_id,
                    "timestamp": row.timestamp.isoformat(),
                    "status": row.status,
                    "safe_metadata": row.safe_metadata,
                    "correlation_id": row.correlation_id,
                }
                for row in rows
            ]

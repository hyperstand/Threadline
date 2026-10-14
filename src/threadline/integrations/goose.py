"""Goose/MCP adapter, fake implementation for tests, and read-only tool policy."""

from __future__ import annotations

import itertools
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from threadline.config import Settings
from threadline.redact import redact_secrets


READ_ONLY_TOOLS = [
    "get_service_status",
    "read_application_logs",
    "get_deployment_metadata",
]


@dataclass(frozen=True)
class ToolInvocation:
    tool_name: str
    target_system: str
    target_environment: str
    result: dict[str, Any]


class GooseToolPolicy:
    def __init__(self, allowed_tools: list[str] | None = None):
        self.allowed_tools = set(allowed_tools or READ_ONLY_TOOLS)
        self.read_only = True

    def validate(self, tool_name: str, target_system: str | None, target_environment: str | None) -> None:
        if tool_name not in self.allowed_tools:
            raise ValueError(f"Unapproved Goose tool: {tool_name}")
        if not target_system or not target_environment:
            raise ValueError("Target system and environment are required for Goose tool scope.")
        if not self.read_only:
            raise ValueError("State-changing Goose tools are not allowed in the MVP.")


class FakeGooseAdapter:
    def __init__(self, policy: GooseToolPolicy | None = None):
        self.policy = policy or GooseToolPolicy()
        self.adapter_name = "fake"

    def list_tools(self) -> list[str]:
        return sorted(self.policy.allowed_tools)

    def invoke(
        self,
        tool_name: str,
        *,
        target_system: str,
        target_environment: str,
    ) -> dict[str, Any]:
        self.policy.validate(tool_name, target_system, target_environment)
        if tool_name == "get_service_status":
            result = {
                "service": target_system,
                "environment": target_environment,
                "status": "available",
                "health": "green",
            }
        elif tool_name == "get_deployment_metadata":
            result = {
                "service": target_system,
                "environment": target_environment,
                "version": "1.2.3-fake",
                "deployed_at": "2026-10-14T00:00:00+00:00",
            }
        elif tool_name == "read_application_logs":
            result = {
                "service": target_system,
                "environment": target_environment,
                "entries": [
                    "INFO service started",
                    "WARN dependency latency elevated",
                ],
            }
        else:
            result = {"status": "unknown", "tool": tool_name}
        return _redact_payload(
            {
                "adapter": self.adapter_name,
                "tool_name": tool_name,
                "target_system": target_system,
                "target_environment": target_environment,
                "observed_at": "2026-10-14T00:00:00+00:00",
                "status": "observed",
                "result": result,
            }
        )


class RealGooseAdapter:
    """Small MCP/JSON-RPC stdio client for an externally configured Goose server."""

    def __init__(
        self,
        command: list[str] | tuple[str, ...],
        *,
        policy: GooseToolPolicy | None = None,
        timeout_seconds: int = 10,
        max_output_bytes: int = 65536,
        environment: dict[str, str] | None = None,
    ):
        if not command:
            raise ValueError("A Goose command is required.")
        self.command = [str(part) for part in command]
        self.policy = policy or GooseToolPolicy()
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.environment = {str(key): str(value) for key, value in (environment or {}).items()}
        self.adapter_name = "goose-mcp"
        self._ids = itertools.count(1)

    def list_tools(self) -> list[str]:
        server_tools = self._list_remote_tools()
        return sorted({tool for tool in server_tools if tool in self.policy.allowed_tools})

    def is_available(self) -> bool:
        try:
            self._initialize()
            return True
        except Exception:
            return False

    def invoke(
        self,
        tool_name: str,
        *,
        target_system: str,
        target_environment: str,
    ) -> dict[str, Any]:
        self.policy.validate(tool_name, target_system, target_environment)
        raw_result = self._call_tool(tool_name, target_system, target_environment)
        observed_at = datetime.now(UTC).isoformat()
        return _redact_payload(
            {
                "adapter": self.adapter_name,
                "tool_name": tool_name,
                "target_system": target_system,
                "target_environment": target_environment,
                "observed_at": observed_at,
                "status": "observed",
                "result": raw_result,
            }
        )

    def _initialize(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "threadline", "version": "m7"},
                },
            }
        ]
        responses = self._exchange(requests)
        if not any(isinstance(item, dict) and item.get("id") == 1 for item in responses):
            raise RuntimeError("Goose did not return an initialize response.")
        self._exchange([{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}])

    def _list_remote_tools(self) -> list[str]:
        self._initialize()
        requests = [
            {"jsonrpc": "2.0", "id": next(self._ids), "method": "tools/list", "params": {}}
        ]
        responses = self._exchange(requests)
        for item in reversed(responses):
            if not isinstance(item, dict) or item.get("id") != requests[0]["id"]:
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                return []
            tools = result.get("tools", [])
            if isinstance(tools, list):
                return [str(tool.get("name")) for tool in tools if isinstance(tool, dict) and tool.get("name")]
        return []

    def _call_tool(self, tool_name: str, target_system: str, target_environment: str) -> Any:
        self._initialize()
        request_id = next(self._ids)
        arguments = {
            "target_system": target_system,
            "target_environment": target_environment,
        }
        requests = [
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ]
        responses = self._exchange(requests)
        for item in reversed(responses):
            if not isinstance(item, dict) or item.get("id") != request_id:
                continue
            if "error" in item:
                raise RuntimeError(str(item.get("error")))
            result = item.get("result")
            if isinstance(result, dict) and result.get("isError") is True:
                content = result.get("content", [])
                raise RuntimeError(_text_from_mcp_content(content) or "Goose tool returned an error.")
            return _normalize_mcp_result(result)
        raise RuntimeError("Goose did not return a tool result.")

    def _exchange(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        request_text = "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages)
        env = os.environ.copy()
        env.update(self.environment)
        try:
            completed = subprocess.run(
                self.command,
                input=request_text,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Goose command is unavailable: {self.command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Goose command timed out after {self.timeout_seconds} seconds.") from exc
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        byte_count = len(stdout.encode("utf-8", errors="replace")) + len(stderr.encode("utf-8", errors="replace"))
        if byte_count > self.max_output_bytes:
            raise RuntimeError("Goose response exceeded the configured output limit.")
        if completed.returncode != 0 and not stdout:
            raise RuntimeError(f"Goose command failed: {redact_secrets(stderr.strip()) or returncode_to_text(completed.returncode)}")
        return _parse_json_objects(stdout)

    def available_command(self) -> bool:
        if not os.path.isfile(self.command[0]):
            return any(
                os.access(candidate, os.X_OK)
                for candidate in _command_candidates(self.command[0])
            )
        return os.access(self.command[0], os.X_OK)


def _command_candidates(name: str) -> list[str]:
    import shutil
    found = shutil.which(name)
    return [found] if found else []


def returncode_to_text(code: int) -> str:
    return f"exit code {code}"


def _parse_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        try:
            obj, end = decoder.raw_decode(text[cursor:])
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            objects.append(obj)
        cursor += end
    return objects


def _text_from_mcp_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    values = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            values.append(str(item.get("text", "")))
    return "\n".join(values)


def _normalize_mcp_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    text = _text_from_mcp_content(content)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if parsed is not None:
        return parsed
    if text:
        return {"text": text}
    return result


def _redact_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return redact_secrets(payload)
    if isinstance(payload, dict):
        return {key: _redact_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_redact_payload(item) for item in payload]
    return payload


def _validate_real_command(command: list[str]) -> None:
    if not command:
        raise ValueError("A Goose command is required.")


def create_goose_adapter(settings: Settings, policy: GooseToolPolicy | None = None) -> FakeGooseAdapter | RealGooseAdapter | None:
    effective_policy = policy or GooseToolPolicy()
    if not settings.goose_enabled:
        return FakeGooseAdapter(effective_policy)
    command = shlex.split(settings.goose_command) if settings.goose_command.strip() else ["goose"]
    try:
        adapter = RealGooseAdapter(
            command=command,
            policy=effective_policy,
            timeout_seconds=settings.goose_tool_timeout_seconds,
            max_output_bytes=settings.goose_max_output_bytes,
        )
    except ValueError:
        return None
    return adapter if adapter.is_available() else None

"""Outbound MCP client to MCDK's embedded server.

This process is both an MCP *server* (to the agent, over stdio) and an MCP
*client* (to MCDK, over SSE). MCDK is the only sanctioned way to run code in
the game, via its ``execute_code`` tool.

Connection lifetime is **task-scoped, never persisted across calls**. The SSE
transport is built on an anyio task group whose cancel scope is *task-affine*:
it must be entered and exited in the same asyncio task. FastMCP runs every tool
call in its own task, so a session opened in one handler's task cannot be reused
from another's without tripping anyio's "exit cancel scope in a different task"
error (which deadlocks the handler). Instead:

* a handler that fires many calls (capture / fps poll loops) wraps them in one
  ``session_scope`` — open + close happen in that handler's task;
* a bare ``call_tool`` opens a short-lived connection just for that one call.

A lock serializes everything: the profiler is a single global engine resource,
so only one capture runs at a time.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from .config import McdkConfig, load_config
from .errors import Reason, TracyError

CONNECT_TIMEOUT_S = 8.0


class McdkClient:
    """Lock-guarded, task-scoped MCP client to MCDK's SSE endpoint."""

    def __init__(
        self,
        explicit_path: str | None = None,
        project_dir: str | None = None,
        override_url: str | None = None,
    ) -> None:
        self._explicit_path = explicit_path
        self._project_dir = project_dir
        self._override_url = override_url
        self._lock = asyncio.Lock()
        # Active session for the current scope, task-local so concurrent handlers
        # never observe each other's connection.
        self._scope_var: contextvars.ContextVar = contextvars.ContextVar(
            "tracy_scope_session", default=None
        )
        self._cfg: McdkConfig | None = None

    # -- config ---------------------------------------------------------------

    def resolve_config(self, require_enabled: bool = True) -> McdkConfig:
        """Resolve (and cache) the MCDK endpoint config. Raises typed errors."""
        cfg = load_config(
            explicit_path=self._explicit_path,
            project_dir=self._project_dir,
            override_url=self._override_url,
            require_enabled=require_enabled,
        )
        self._cfg = cfg
        return cfg

    async def reconfigure(self, project_dir: str | None = None, override_url: str | None = None) -> None:
        """Re-point the client (e.g. a different project's .mcdev.json). The next
        call resolves the new endpoint; connections are per-call/scope, so there
        is no open session to drop."""
        async with self._lock:
            if project_dir is not None:
                self._project_dir = project_dir
            if override_url is not None:
                self._override_url = override_url
            self._cfg = None

    # -- connection lifecycle -------------------------------------------------

    async def _connect(self, stack: AsyncExitStack) -> ClientSession:
        """Open an SSE session on ``stack``.

        The caller MUST enter and exit ``stack`` within a single asyncio task
        (anyio cancel scopes are task-affine). Only ``session_scope`` and the
        single-shot branch of ``call_tool`` call this — never to build a
        long-lived shared session.
        """
        cfg = self.resolve_config(require_enabled=True)  # TracyError -> propagate
        try:
            read, write = await stack.enter_async_context(sse_client(cfg.sse_url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT_S)
            return session
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise TracyError(
                Reason.MCDK_UNREACHABLE,
                f"timed out connecting to MCDK MCP at {cfg.sse_url}; is the game "
                f"running via mcdk.exe?",
                url=cfg.sse_url,
            ) from exc
        except Exception as exc:  # connection refused, DNS, protocol, etc.
            raise TracyError(
                Reason.MCDK_UNREACHABLE,
                f"cannot reach MCDK MCP at {cfg.sse_url}: {exc!r}",
                url=cfg.sse_url,
            ) from exc

    @asynccontextmanager
    async def session_scope(self):
        """Hold one connection for an entire tool handler.

        Enter and exit run in the same task (the handler's), so anyio's
        task-group cancel scope stays valid. Every ``call_tool`` inside the
        scope reuses this one connection — essential for the capture/fps poll
        loops that fire dozens of ``execute_code`` calls. Nested scopes reuse
        the outer connection; concurrent handlers serialize on the lock.
        """
        if self._scope_var.get() is not None:
            yield  # reuse the connection opened by an outer scope (same task)
            return
        async with self._lock:
            async with AsyncExitStack() as stack:
                session = await self._connect(stack)
                token = self._scope_var.set(session)
                try:
                    yield
                finally:
                    self._scope_var.reset(token)

    async def aclose(self) -> None:
        """No persistent connection to close — each scope/call owns its own."""
        return None

    # -- tool invocation ------------------------------------------------------

    async def call_tool(
        self, name: str, arguments: dict[str, Any], timeout_s: float = 30.0
    ) -> Any:
        """Call an MCDK tool; return the parsed text payload.

        Inside a ``session_scope`` this reuses the handler's connection; outside
        one it opens a short-lived connection for just this call. Either way the
        connection's enter/exit stay within the calling task.
        """
        scoped = self._scope_var.get()
        if scoped is not None:
            return await self._call_on(scoped, name, arguments, timeout_s)
        async with self._lock:
            async with AsyncExitStack() as stack:
                session = await self._connect(stack)
                return await self._call_on(session, name, arguments, timeout_s)

    async def _call_on(
        self, session: ClientSession, name: str, arguments: dict[str, Any], timeout_s: float
    ) -> Any:
        """Run one tool call on an open session, mapping timeouts to typed errors."""
        try:
            return await self._invoke(session, name, arguments, timeout_s)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise TracyError(
                Reason.EXECUTE_TIMEOUT,
                f"MCDK tool '{name}' did not return within {timeout_s:.0f}s",
            ) from exc

    async def _invoke(
        self, session: ClientSession, name: str, arguments: dict[str, Any], timeout_s: float
    ) -> str | None:
        """Call an MCDK tool and return its raw text payload (callers parse)."""
        result = await asyncio.wait_for(
            session.call_tool(name, arguments), timeout=timeout_s
        )
        text = _extract_text(result)
        if getattr(result, "isError", False):
            lowered = (text or "").lower()
            if "timeout" in lowered or "timed out" in lowered:
                raise TracyError(Reason.EXECUTE_TIMEOUT, text or f"{name} timed out")
            if any(
                s in lowered
                for s in ("not be in the game", "unavailable", "not connected", "no client")
            ):
                raise TracyError(
                    Reason.GAME_NOT_CONNECTED,
                    text or "the game is not attached to MCDK",
                )
            raise TracyError(
                Reason.SNIPPET_ERROR, text or f"MCDK reported an error for '{name}'"
            )
        return text

    # -- high-level: run Py2 in the game --------------------------------------

    async def execute_code(
        self,
        code: str,
        is_client: bool = True,
        direct_return: bool = True,
        timeout_s: float = 20.0,
    ) -> Any:
        """Run a Py2 snippet in the game; return the decoded ``return_value``.

        MCDK's ``execute_code`` wraps the result as a human-readable string ending
        with ``Return value JSON: <json>`` (see MCDevTool main.cpp). We extract and
        decode that JSON. The in-game thread timeout is 10s (not configurable via
        the tool), so callers must keep each snippet fast.
        """
        text = await self.call_tool(
            "execute_code",
            {"code": code, "is_client": is_client, "direct_return": direct_return},
            timeout_s=timeout_s,
        )
        return parse_execute_result(text)


def _extract_text(result: Any) -> str | None:
    """Pull the first text block out of an MCP CallToolResult."""
    content = getattr(result, "content", None)
    if not content:
        return None
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts) if parts else None


_RETURN_VALUE_MARKER = "Return value JSON: "


def parse_execute_result(text: str | None) -> Any:
    """Decode the ``return_value`` JSON out of MCDK's execute_code text payload.

    MCDK formats success as::

        Code executed successfully on client.
        Return type: dict
        Return repr: {...}
        Return value JSON: { ...the actual value... }

    We slice after the marker and JSON-decode. Falls back to the raw text if the
    marker is absent (older MCDK or unexpected formatting).
    """
    if text is None:
        return None
    idx = text.rfind(_RETURN_VALUE_MARKER)
    if idx == -1:
        return _parse_payload(text)
    blob = text[idx + len(_RETURN_VALUE_MARKER):].strip()
    try:
        return json.loads(blob)
    except ValueError:
        return blob


def _parse_payload(text: str | None) -> Any:
    """Best-effort: JSON-decode the tool text, else return the raw string."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except ValueError:
        return text

"""Run a built snippet in the game and normalize its result.

Snippets return a dict; on internal failure they return a dict carrying
``__tracy_error__`` (a traceback tail) rather than raising. This helper turns
that marker into a typed :class:`TracyError` so tool handlers see a uniform
contract: success dict, or exception.
"""

from __future__ import annotations

from typing import Any

from ..errors import Reason, TracyError
from ..mcdk_client import McdkClient


async def run_snippet(
    client: McdkClient,
    code: str,
    is_client: bool = True,
    timeout_s: float = 20.0,
) -> Any:
    """Execute ``code`` in the game; return the decoded dict or raise TracyError."""
    result = await client.execute_code(
        code, is_client=is_client, direct_return=True, timeout_s=timeout_s
    )
    if isinstance(result, dict) and "__tracy_error__" in result:
        raise TracyError(
            Reason.SNIPPET_ERROR,
            "in-game snippet raised an exception",
            traceback=result.get("__tracy_error__"),
        )
    return result

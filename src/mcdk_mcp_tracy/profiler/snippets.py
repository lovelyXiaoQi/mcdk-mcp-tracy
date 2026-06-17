"""Builders for the Py2 snippets injected into the game via ``execute_code``.

Only the FPS / frame-time sampler remains (used by ``tracy_jank_fps`` ->
``operations.sample_fps``). The per-function CPU-profiler snippets
(getCpuFrameData / enableCpuProfiler / set_white_modules) were removed: those
bindings are absent on release builds. Use ``tracy_native_capture`` (native
Tracy on TCP 8086) for per-function timing instead.

Hard constraints baked in here (verified against MCDevTool / IPCSystem.py):

* The code runs on the game **main thread** with a fixed **10s** timeout
  (``execute_code`` does not forward a timeout param). So snippets must be fast
  and must NOT ``time.sleep`` — blocking the main thread freezes the game.
* ``execute_code`` returns the value of a single trailing expression, OR the
  global ``_result`` if the code is statements. We therefore always end with
  ``_result = __tracy_xxx(...)`` and never use a top-level ``return``.
* Pure Python-2 runtime (no f-strings, no Py3-only names). Snippet *content* is
  a fixed constant; only the trailing call line carries substituted literals,
  built with :func:`py_literal` so values are valid Py2 literals (``True`` /
  ``False`` / ``None`` rather than JSON ``true`` / ``false`` / ``null``).
* Every function returns a dict; on failure it returns ``{"__tracy_error__": ..}``
  instead of raising, so the server can surface a clean error.
"""

from __future__ import annotations

import json
from typing import Any


def py_literal(value: Any) -> str:
    """Render a Python value as a Py2-safe source literal.

    Booleans/None must become ``True``/``False``/``None`` (NOT JSON), so we do
    not use ``json.dumps`` for them. Strings reuse ``json.dumps`` (a JSON string
    is also a valid Python string literal).
    """
    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "None"
    if isinstance(value, bool):  # unreachable, kept for clarity
        return "True" if value else "False"
    if isinstance(value, int):
        return repr(int(value))
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(py_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(py_literal(k) + ": " + py_literal(v) for k, v in value.items()) + "}"
    raise TypeError("cannot render literal for type %r" % type(value).__name__)


def _call(fn: str, *args: Any) -> str:
    return "\n_result = %s(%s)\n" % (fn, ", ".join(py_literal(a) for a in args))


# --------------------------------------------------------------------------- #
# FPS / frame-time sampler (used by tracy_jank_fps -> operations.sample_fps)
# --------------------------------------------------------------------------- #

_FPS_DEF = r'''
def __tracy_fps():
    out = {"ok": False}
    try:
        import _utility
        out["fps"] = (_utility.get_Fps() if hasattr(_utility, "get_Fps") else None)
        out["frame_time"] = (_utility.get_frame_time() if hasattr(_utility, "get_frame_time") else None)
        out["ok"] = True
    except Exception:
        import traceback
        out["__tracy_error__"] = traceback.format_exc()[-400:]
    return out
'''


def build_fps_sample() -> str:
    return _FPS_DEF + _call("__tracy_fps")

"""Snippets must be valid, Py2-safe source ending in `_result = ...`.

We compile under Py3 as a syntax proxy (the snippets deliberately avoid
constructs that differ between Py2 and Py3: no print-statement, no f-strings,
`except ... as e`). f-strings are explicitly banned because the game runs Py2.

Only the FPS sampler snippet remains; per-function profiling now uses the
native-Tracy path, which injects no Py2 snippets.
"""

import re

import pytest

from mcdk_mcp_tracy.profiler import snippets


ALL_SNIPPETS = {
    "fps": snippets.build_fps_sample(),
}


@pytest.mark.parametrize("name,code", list(ALL_SNIPPETS.items()))
def test_compiles(name, code):
    compile(code, f"<{name}>", "exec")


@pytest.mark.parametrize("name,code", list(ALL_SNIPPETS.items()))
def test_assigns_result_and_no_toplevel_return(name, code):
    assert "\n_result = " in code, "snippet must assign _result (execute_code contract)"
    # no top-level `return` (would be a SyntaxError in eval/exec mode)
    for line in code.splitlines():
        assert not line.startswith("return "), "no top-level return allowed"


@pytest.mark.parametrize("name,code", list(ALL_SNIPPETS.items()))
def test_no_fstrings(name, code):
    # crude but effective: no f"..." / f'...' prefixes anywhere in snippet source
    assert not re.search(r"""(^|[^A-Za-z0-9_])f["']""", code), "f-strings are not Py2-safe"


def test_py_literal_booleans_and_none():
    assert snippets.py_literal(True) == "True"
    assert snippets.py_literal(False) == "False"
    assert snippets.py_literal(None) == "None"


def test_py_literal_collections_use_python_bools():
    out = snippets.py_literal([True, False, None, 3, 1.5])
    assert out == "[True, False, None, 3, 1.5]"
    d = snippets.py_literal({"a": True})
    assert d == '{"a": True}'


def test_py_literal_strings_are_escaped():
    assert snippets.py_literal('a"b') == '"a\\"b"'

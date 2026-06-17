from mcdk_mcp_tracy.mcdk_client import parse_execute_result


def test_extracts_json_after_marker():
    text = (
        "Code executed successfully on client.\n"
        "Return type: dict\n"
        "Return repr: {'ok': True}\n"
        'Return value JSON: {\n  "ok": true,\n  "top": []\n}'
    )
    out = parse_execute_result(text)
    assert out == {"ok": True, "top": []}


def test_scalar_value():
    text = "Code executed successfully on client.\nReturn value JSON: null"
    assert parse_execute_result(text) is None
    text2 = "x\nReturn value JSON: 42"
    assert parse_execute_result(text2) == 42


def test_uses_last_marker_occurrence():
    text = "Return value JSON: {\"a\": 1} ... Return value JSON: {\"b\": 2}"
    assert parse_execute_result(text) == {"b": 2}


def test_no_marker_falls_back_to_raw():
    assert parse_execute_result("plain text") == "plain text"
    assert parse_execute_result('{"a": 1}') == {"a": 1}


def test_none():
    assert parse_execute_result(None) is None

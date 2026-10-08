import pytest

from harness.tools import MAX_TOOL_OUTPUT, bash, default_tools, list_dir, read_file, truncate


def test_registry_exposes_schema():
    registry = default_tools()
    assert registry.names() == ["read_file", "list_dir", "bash"]

    definitions = registry.definitions()
    assert [d["name"] for d in definitions] == ["read_file", "list_dir", "bash"]
    # What the model sees: name, description, JSON schema -- and nothing else.
    assert set(definitions[0]) == {"name", "description", "input_schema"}
    assert definitions[0]["input_schema"]["required"] == ["path"]


def test_registry_run_unknown_tool():
    with pytest.raises(LookupError, match="no such tool"):
        default_tools().run("nope", {})


def test_read_file(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_text("content")

    assert read_file().handler({"path": str(path)}) == "content"
    with pytest.raises(OSError):
        read_file().handler({"path": str(tmp_path / "missing")})


def test_list_dir_defaults_to_working_directory(tmp_path, monkeypatch):
    for name in ("b.txt", "a.txt"):
        (tmp_path / name).write_text("")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)

    # An omitted "path" must not be an error -- the schema marks it optional.
    assert list_dir().handler({}) == "a.txt\nb.txt\nsub/"


def test_bash():
    assert bash().handler({"command": "echo hi"}).strip() == "hi"

    # A non-zero exit is an error the model should see, with output attached.
    with pytest.raises(RuntimeError, match="boom"):
        bash().handler({"command": "echo boom >&2; exit 3"})

    with pytest.raises(ValueError):
        bash().handler({"command": "  "})


def test_truncate_caps_tool_output():
    long = truncate("x" * (MAX_TOOL_OUTPUT + 100))
    assert len(long) > MAX_TOOL_OUTPUT
    assert "truncated" in long
    assert truncate("small") == "small"

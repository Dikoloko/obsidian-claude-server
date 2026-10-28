"""The hardening of this fork (Windows desktop behind a tunnel, reached by Claude).

Each test pins one change against the upstream code:
- path checks: Windows short names, UNC and drive paths, device names, trailing dots,
  and a second dot check on the resolved path;
- text writes only create .md and .canvas files;
- vault_write creates only, unless asked to overwrite or to merge frontmatter;
- batch frontmatter, binary writes, canvas tools and signed URLs are gone;
- move and delete are back (27/10/2026): delete goes to .trash, folders included, a move
  keeps the file type, and the vault root can be neither moved nor deleted;
- .claude is hidden from listings;
- search matches the query literally.
"""

import asyncio
import ctypes
import json
import os
import pathlib
import sys

import pytest

from obsidian_vault_mcp import config, server, vault
from obsidian_vault_mcp.tools import search
from obsidian_vault_mcp.vault import list_directory, resolve_vault_path, write_file_atomic


def call_tool(name: str, arguments: dict) -> dict:
    result = asyncio.run(server.mcp.call_tool(name, arguments))
    result = result.content
    return json.loads("".join(getattr(block, "text", "") for block in result))


def _short_name(path: pathlib.Path) -> str | None:
    """The 8.3 short name of an existing path, or None when the volume has none."""
    if sys.platform != "win32":
        return None
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)):
        return None
    short = pathlib.Path(buf.value).name
    return None if short == path.name else short


# --- path checks -----------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "OBSIDI~1/plugins/x/main.js",
    "GIT~1/hooks/pre-commit.md",
    "sub/CLAUDE~1/settings.md",
])
def test_short_name_shapes_are_refused(vault_dir, bad):
    with pytest.raises(ValueError, match="short name"):
        resolve_vault_path(bad)


def test_resolved_path_into_hidden_dir_is_refused(vault_dir, monkeypatch):
    """Second layer: even when the raw check lets a short name through, the resolved
    path is checked again and ends in .obsidian."""
    short = _short_name(vault_dir / ".obsidian")
    if short is None:
        pytest.skip("this volume has no 8.3 short names")
    monkeypatch.setattr(vault, "_check_raw_path", lambda p: None)
    with pytest.raises(ValueError, match="hidden"):
        resolve_vault_path(f"{short}/config.json")


@pytest.mark.parametrize("bad", [
    "//evil.example/share/note.md",
    "\\\\evil.example\\share\\note.md",
    "/absolute.md",
    "\\rooted.md",
    "C:/Windows/win.md",
    "C:relative.md",
    "note.md:hidden-stream",
])
def test_unc_drive_and_absolute_paths_are_refused_before_resolving(vault_dir, monkeypatch, bad):
    """Refused without touching the filesystem: resolving a UNC path would already
    open an SMB connection to that host."""
    def no_resolve(self, *a, **k):
        raise AssertionError(f"resolve() reached for {bad!r}")

    monkeypatch.setattr(pathlib.Path, "resolve", no_resolve)
    with pytest.raises(ValueError):
        resolve_vault_path(bad)


@pytest.mark.parametrize("bad", ["CON.md", "nul", "sub/com1.md", "LPT9.md", "note.md.", "note.md ", "dir./x.md"])
def test_device_names_and_trailing_dots_are_refused(vault_dir, bad):
    with pytest.raises(ValueError):
        resolve_vault_path(bad)


@pytest.mark.parametrize("ok", ["test-note.md", "subfolder/nested-note.md", "", "Console notes.md", "a.b.c.md"])
def test_ordinary_paths_still_resolve(vault_dir, ok):
    assert resolve_vault_path(ok).is_relative_to(vault_dir.resolve())


# --- text writes -----------------------------------------------------------------


@pytest.mark.parametrize("bad", ["run.bat", "run.ps1", "link.url", "desktop.ini", "script.js", "noext"])
def test_text_writes_refuse_non_note_types(vault_dir, bad):
    with pytest.raises(ValueError, match="only these file types"):
        write_file_atomic(bad, "x")
    assert not (vault_dir / bad).exists()


def test_text_write_leaves_no_visible_temp_file(vault_dir):
    write_file_atomic("fresh.md", "hello\n")
    assert (vault_dir / "fresh.md").read_text(encoding="utf-8") == "hello\n"
    assert [p.name for p in vault_dir.iterdir() if p.suffix == ".tmp"] == []


def test_append_refuses_non_note_types(vault_dir):
    result = call_tool("vault_append", {"path": "evil.ps1", "content": "Start-Process calc"})
    assert "error" in result
    assert not (vault_dir / "evil.ps1").exists()


# --- vault_write defaults ----------------------------------------------------------


def test_vault_write_does_not_replace_by_default(vault_dir):
    (vault_dir / "n.md").write_text("old\n", encoding="utf-8")
    result = call_tool("vault_write", {"path": "n.md", "content": "new\n"})
    assert "error" in result and result["created"] is False
    assert (vault_dir / "n.md").read_text(encoding="utf-8") == "old\n"


def test_vault_write_replaces_when_asked(vault_dir):
    (vault_dir / "n.md").write_text("old\n", encoding="utf-8")
    result = call_tool("vault_write", {"path": "n.md", "content": "new\n", "overwrite": True})
    assert "error" not in result
    assert (vault_dir / "n.md").read_text(encoding="utf-8") == "new\n"


def test_vault_write_merge_frontmatter_updates_existing(vault_dir):
    result = call_tool("vault_write", {
        "path": "test-note.md",
        "content": "---\nstatus: done\n---\n\nNew body.\n",
        "merge_frontmatter": True,
    })
    assert "error" not in result
    text = (vault_dir / "test-note.md").read_text(encoding="utf-8")
    assert "status: done" in text and "type: note" in text


def test_vault_write_creates_new_note(vault_dir):
    result = call_tool("vault_write", {"path": "inbox/idea.md", "content": "idea\n"})
    assert result["created"] is True


def test_vault_edit_still_replaces_text(vault_dir):
    result = call_tool("vault_edit", {
        "path": "test-note.md",
        "edits": [{"old_text": "some content", "new_text": "other content"}],
    })
    assert "error" not in result
    assert "other content" in (vault_dir / "test-note.md").read_text(encoding="utf-8")


# --- tool surface ----------------------------------------------------------------


REMOVED_TOOLS = [
    "vault_write_binary",
    "vault_batch_frontmatter_update",
    "vault_canvas_read",
    "vault_canvas_add_node",
    "vault_canvas_add_edge",
    "vault_request_upload_url",
    "vault_request_download_url",
]


@pytest.mark.parametrize("name", REMOVED_TOOLS)
def test_risky_tools_are_not_registered(name):
    assert server.mcp._tool_manager.get_tool(name) is None


# --- move and delete (back since 27/10/2026, with fork rules) ----------------------


@pytest.mark.parametrize("name", ["vault_move", "vault_delete"])
def test_move_and_delete_are_registered(name):
    assert server.mcp._tool_manager.get_tool(name) is not None


@pytest.mark.parametrize("destination", ["run.bat", "start.ps1", "link.url", "desktop.ini", "note", "note.txt"])
def test_move_cannot_change_the_file_type(vault_dir, destination):
    result = call_tool("vault_move", {"source": "test-note.md", "destination": destination})
    assert "cannot change the file type" in result.get("error", ""), result
    assert (vault_dir / "test-note.md").exists() and not (vault_dir / destination).exists()


@pytest.mark.parametrize("destination", [".obsidian/x.md", "OBSIDI~1/x.md", "../outside.md", "C:/x.md"])
def test_move_cannot_leave_the_visible_vault(vault_dir, destination):
    result = call_tool("vault_move", {"source": "test-note.md", "destination": destination})
    assert "error" in result, result
    assert (vault_dir / "test-note.md").exists()


def test_move_renames_a_note_and_repoints_links(vault_dir):
    (vault_dir / "linker.md").write_text("See [[test-note]].\n", encoding="utf-8")
    result = call_tool("vault_move", {"source": "test-note.md", "destination": "archief/renamed.md"})
    assert result.get("moved") is True, result
    assert (vault_dir / "archief" / "renamed.md").exists()
    linker = (vault_dir / "linker.md").read_text(encoding="utf-8")
    assert "[[test-note]]" not in linker and "renamed]]" in linker, linker


def test_move_takes_a_whole_folder(vault_dir):
    result = call_tool("vault_move", {"source": "subfolder", "destination": "archief/subfolder"})
    assert result.get("moved") is True, result
    assert (vault_dir / "archief" / "subfolder" / "nested-note.md").exists()


@pytest.mark.parametrize("tool,arguments", [
    ("vault_move", {"source": ".", "destination": "x"}),
    ("vault_move", {"source": "/", "destination": "x"}),
    ("vault_delete", {"path": ".", "confirm": True}),
    ("vault_delete", {"path": "/", "confirm": True}),
])
def test_the_vault_root_cannot_be_moved_or_deleted(vault_dir, tool, arguments):
    result = call_tool(tool, arguments)
    assert "error" in result, result
    assert (vault_dir / "test-note.md").exists()


def test_the_root_guard_holds_below_the_tools(vault_dir):
    """The tools refuse an empty path in their input model; the vault functions refuse it too."""
    with pytest.raises(ValueError, match="vault root"):
        vault.move_path("", "x")
    with pytest.raises(ValueError, match="vault root"):
        vault.delete_path("")
    assert (vault_dir / "test-note.md").exists()


def test_delete_needs_confirm(vault_dir):
    result = call_tool("vault_delete", {"path": "test-note.md"})
    assert "confirm=true" in result.get("error", ""), result
    assert (vault_dir / "test-note.md").exists()


def test_delete_moves_a_note_to_the_trash(vault_dir):
    result = call_tool("vault_delete", {"path": "test-note.md", "confirm": True})
    assert result.get("deleted") is True, result
    assert not (vault_dir / "test-note.md").exists()
    assert (vault_dir / ".trash" / "test-note.md").exists()


def test_delete_moves_a_whole_folder_to_the_trash(vault_dir):
    result = call_tool("vault_delete", {"path": "subfolder", "confirm": True})
    assert result.get("deleted") is True, result
    assert (vault_dir / ".trash" / "subfolder" / "nested-note.md").exists()
    assert not (vault_dir / "subfolder").exists()


def test_the_trash_stays_out_of_reach(vault_dir):
    call_tool("vault_delete", {"path": "test-note.md", "confirm": True})
    assert "error" in call_tool("vault_read", {"path": ".trash/test-note.md"})
    assert "error" in call_tool("vault_delete", {"path": ".trash/test-note.md", "confirm": True})


def test_signed_routes_stay_off_even_with_secrets(monkeypatch):
    monkeypatch.setattr(config, "VAULT_UPLOAD_URL_SECRET", "set")
    monkeypatch.setattr(config, "VAULT_DOWNLOAD_URL_SECRET", "set")
    assert config.signed_upload_enabled() is False
    assert config.signed_download_enabled() is False


def test_claude_dir_is_hidden_from_listings(vault_dir):
    (vault_dir / ".claude").mkdir()
    (vault_dir / ".claude" / "settings.json").write_text("{}")
    names = {entry["name"] for entry in list_directory("", depth=3)}
    assert ".claude" not in names and "settings.json" not in names


# --- search ----------------------------------------------------------------------


def test_python_search_is_literal(vault_dir):
    (vault_dir / "lang.md").write_text("Notes on C++ (draft)\n", encoding="utf-8")
    hits = search._search_python("C++ (draft)", vault_dir, "*.md", 10, 0)
    assert any(h.get("path", "").endswith("lang.md") for h in hits)


def test_ripgrep_search_is_literal(vault_dir, monkeypatch):
    captured = {}

    class Done:
        returncode = 1
        stdout = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return Done()

    monkeypatch.setattr(search.subprocess, "run", fake_run)
    search._search_ripgrep("C++", vault_dir.resolve(), "*.md", 10, 0)
    assert "--fixed-strings" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-e") + 1] == "C++"


# --- paths come back with "/" on Windows too ---------------------------------------


@pytest.fixture
def nested_note(vault_dir):
    (vault_dir / "Trips" / "2026").mkdir(parents=True)
    (vault_dir / "Trips" / "2026" / "NYC.md").write_text("---\ntype: trip\n---\nhello nyc\n", encoding="utf-8")


def test_search_paths_use_forward_slashes(nested_note, vault_dir):
    content = search._search_python("hello nyc", vault_dir, "*.md", 10, 0)
    names = search._search_filenames("nyc", vault_dir, "*.md", 10)
    assert [h["path"] for h in content] == ["Trips/2026/NYC.md"]
    assert [h["path"] for h in names] == ["Trips/2026/NYC.md"]


def test_listing_paths_use_forward_slashes(nested_note):
    paths = {entry["path"] for entry in list_directory("", depth=3)}
    assert "Trips/2026/NYC.md" in paths and not any("\\" in p for p in paths)


@pytest.mark.parametrize("prefix", ["Trips/", "Trips\\2026"])
def test_frontmatter_search_within_a_folder(nested_note, prefix):
    from obsidian_vault_mcp.frontmatter_index import FrontmatterIndex

    index = FrontmatterIndex()
    index.rebuild()
    results = index.search_by_field("type", "trip", "exact", path_prefix=prefix)
    assert [r["path"] for r in results] == ["Trips/2026/NYC.md"]

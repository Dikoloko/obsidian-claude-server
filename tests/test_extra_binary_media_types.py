"""Operator-added binary media types (#100).

The built-in allowlist accepts images and PDF. VAULT_EXTRA_BINARY_MEDIA_TYPES_JSON adds
types (Office files are the case that asked for it), never removes one, and cannot name a
text extension the write tools own. This fork removed vault_write_binary and the signed
upload route, so only the startup check is left to test; it runs in a child process with
the real environment variable.
"""

import json
import os
import subprocess
import sys

import pytest

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OFFICE = {DOCX: [".docx"], XLSX: [".xlsx"]}


def start(raw: str | None) -> subprocess.CompletedProcess:
    """Run the startup check server.main() runs, in a fresh interpreter with the variable set."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAULT_")}
    env["VAULT_PATH"] = os.getcwd()
    if raw is not None:
        env["VAULT_EXTRA_BINARY_MEDIA_TYPES_JSON"] = raw
    return subprocess.run([sys.executable, "-c", "from obsidian_vault_mcp.config import validate_config; validate_config()"],
                          env=env, capture_output=True, text=True)


@pytest.mark.parametrize("raw,fragment", [
    ("{not json", "not valid JSON"),
    ('[".docx"]', "must be a JSON object"),
    ('{"a/b": ".docx"}', "non-empty list"),
    ('{"a/b": []}', "non-empty list"),
    ('{"a/b": ["docx"]}', "leading dot"),
    ('{"text/markdown": [".md"]}', "cannot be a binary type"),
    ('{"a/b": [".canvas"]}', "cannot be a binary type"),
    ('{"a/b": [".MD"]}', "cannot be a binary type"),
    ('{"image/svg+xml": [".svg"]}', "cannot be a binary type"),
    ('{"notatype": [".x"]}', "type/subtype"),
])
def test_a_bad_setting_stops_startup_with_its_name(raw, fragment):
    result = start(raw)

    assert result.returncode != 0
    assert "VAULT_EXTRA_BINARY_MEDIA_TYPES_JSON" in result.stderr and fragment in result.stderr, result.stderr[-400:]


@pytest.mark.parametrize("raw", [None, "", json.dumps(OFFICE)])
def test_a_good_or_absent_setting_starts(raw):
    result = start(raw)

    assert result.returncode == 0, result.stderr[-400:]

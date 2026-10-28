"""Both MCP transport paths of mcp 2.x, through the app that serves the vault.

Claude's connector opens with MCP-Protocol-Version 2026-07-28, which mcp 1.x answered
with a 400. mcp 2.x sends that version to a separate per-request path and keeps the
initialize handshake for the older versions. Each test here runs build_app() with the
bearer middleware, so the checks the fork relies on are tested on both paths: the
DNS-rebinding Host and Origin checks, and the read-only refusal at tool dispatch.
"""

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from obsidian_vault_mcp import auth as auth_module
from obsidian_vault_mcp import config, server

LOOPBACK = "http://127.0.0.1:8420"
MODERN = "2026-07-28"
WRITE_TOKEN = "secret-token"
READ_TOKEN = "read-only-token"


@pytest.fixture
def client(vault_dir, monkeypatch):
    monkeypatch.setattr(auth_module, "VAULT_MCP_TOKEN", WRITE_TOKEN)
    monkeypatch.setattr(config, "VAULT_MCP_CF_ACCESS_TEAM_DOMAIN", "")
    monkeypatch.setattr(config, "VAULT_MCP_CF_ACCESS_AUD", "")
    # A per-client token with read access, as vault-mcp-oauth sets it.
    read_client = SimpleNamespace(client_id="read-client", access="read")
    monkeypatch.setattr(
        auth_module, "_per_client_token",
        lambda request, token: read_client if token == READ_TOKEN else None,
    )
    with TestClient(server.build_app(), raise_server_exceptions=False, base_url=LOOPBACK) as test_client:
        yield test_client


def _legacy(client, method, params, token=WRITE_TOKEN, version=None, **headers):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        **({"MCP-Protocol-Version": version} if version else {}),
        **headers,
    }
    return client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _modern(client, method, params, token=WRITE_TOKEN, **headers):
    """A 2026-07-28 request: the version rides in a header and in params._meta, no initialize."""
    params = {
        **params,
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": MODERN,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "protocol-test", "version": "0"},
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MODERN,
        "Mcp-Method": method,
        **({"Mcp-Name": params["name"]} if "name" in params else {}),
        **headers,
    }
    return client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _text(response) -> str:
    return "".join(block.get("text", "") for block in response.json()["result"]["content"])


# --- the legacy handshake still works -------------------------------------------------


@pytest.mark.parametrize("version", [None, "2025-06-18", "2025-11-25"])
def test_legacy_initialize(client, version):
    response = _legacy(client, "initialize", {
        "protocolVersion": version or "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "protocol-test", "version": "0"},
    }, version=version)

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["serverInfo"]["name"] == "obsidian_web_mcp"
    assert result["protocolVersion"] == (version or "2025-06-18")


def test_legacy_tool_call(client):
    response = _legacy(client, "tools/call", {"name": "vault_read", "arguments": {"path": "test-note.md"}},
                       version="2025-11-25")

    assert response.status_code == 200, response.text
    assert "This is a test note" in _text(response)


# --- 2026-07-28 is accepted ----------------------------------------------------------


def test_modern_tools_list(client):
    response = _modern(client, "tools/list", {})

    assert response.status_code == 200, response.text
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"vault_read", "vault_write", "vault_move", "vault_delete"} <= names


def test_modern_tool_call(client):
    response = _modern(client, "tools/call", {"name": "vault_read", "arguments": {"path": "test-note.md"}})

    assert response.status_code == 200, response.text
    assert "This is a test note" in _text(response)


def test_modern_write(client, vault_dir):
    response = _modern(client, "tools/call", {"name": "vault_write",
                                              "arguments": {"path": "nieuw.md", "content": "hallo\n"}})

    assert response.status_code == 200, response.text
    assert (vault_dir / "nieuw.md").read_text(encoding="utf-8") == "hallo\n"


# --- the read-only refusal holds on both paths -----------------------------------------


@pytest.mark.parametrize("send", [
    lambda c, m, p, **kw: _legacy(c, m, p, version="2025-11-25", **kw),
    _modern,
], ids=["legacy", "modern"])
def test_read_only_client_is_refused_a_write(client, vault_dir, send):
    refused = send(client, "tools/call",
                   {"name": "vault_write", "arguments": {"path": "nope.md", "content": "x\n"}}, token=READ_TOKEN)
    allowed = send(client, "tools/call", {"name": "vault_read", "arguments": {"path": "test-note.md"}},
                   token=READ_TOKEN)

    assert refused.status_code == 200, refused.text
    assert "read" in _text(refused).lower()
    assert not (vault_dir / "nope.md").exists()
    assert "This is a test note" in _text(allowed)


# --- DNS-rebinding protection holds on both paths --------------------------------------


@pytest.mark.parametrize("send", [
    lambda c, m, p, **kw: _legacy(c, m, p, version="2025-11-25", **kw),
    _modern,
], ids=["legacy", "modern"])
def test_foreign_host_is_refused(client, send):
    response = send(client, "tools/list", {}, Host="evil.example.com")

    assert response.status_code == 421, response.text


@pytest.mark.parametrize("send", [
    lambda c, m, p, **kw: _legacy(c, m, p, version="2025-11-25", **kw),
    _modern,
], ids=["legacy", "modern"])
def test_foreign_origin_is_refused(client, send):
    response = send(client, "tools/list", {}, Origin="https://evil.example.com")

    assert response.status_code == 403, response.text


def test_operator_host_is_allowed(vault_dir, monkeypatch):
    """A hostname from VAULT_MCP_ALLOWED_HOSTS reaches the modern path; others do not."""
    monkeypatch.setattr(auth_module, "VAULT_MCP_TOKEN", WRITE_TOKEN)
    monkeypatch.setattr(server, "TRANSPORT_SECURITY", server.TRANSPORT_SECURITY.model_copy(
        update={"allowed_hosts": [*server.TRANSPORT_SECURITY.allowed_hosts, "vault.example.com"]}
    ))
    with TestClient(server.build_app(), raise_server_exceptions=False, base_url=LOOPBACK) as test_client:
        allowed = _modern(test_client, "tools/list", {}, Host="vault.example.com")
        refused = _modern(test_client, "tools/list", {}, Host="other.example.com")

    assert allowed.status_code == 200, allowed.text
    assert refused.status_code == 421, refused.text


# --- a refused input value still tells the model why --------------------------------


def test_input_model_reason_reaches_the_model(vault_dir):
    """mcp 2.x hides a tool's exception text; the reason a Vault*Input refuses a value is
    passed on, as under 1.x, so the model can correct its call."""
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(server.mcp.call_tool("vault_search", {"query": "x", "max_results": 100000}))

    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "max_results" in str(excinfo.value)


def test_input_model_reason_over_modern_path(client):
    response = _modern(client, "tools/call", {"name": "vault_search",
                                              "arguments": {"query": "x", "max_results": 100000}})

    assert response.status_code == 200, response.text
    assert response.json()["result"]["isError"] is True
    assert "max_results" in _text(response)


def test_a_crash_keeps_its_text_on_the_server(vault_dir, monkeypatch):
    """Anything else a tool raises stays generic for the client, as mcp 2.x intends."""
    import asyncio

    from mcp.server.mcpserver.exceptions import UnexpectedToolError

    def boom(*args, **kwargs):
        raise RuntimeError("C:/secret/path")

    monkeypatch.setattr(server, "_vault_daily_note_path", boom)
    with pytest.raises(UnexpectedToolError) as excinfo:
        asyncio.run(server.mcp.call_tool("vault_daily_note_path", {}))

    assert "secret" not in str(excinfo.value)

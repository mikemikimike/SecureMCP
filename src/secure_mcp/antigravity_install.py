"""Owned stdio MCP registration; never changes Antigravity authentication."""

import json
from pathlib import Path
import sys

from secure_mcp.encrypted_session import session_file_lock
from secure_mcp.gateway_install import atomic_bytes
from secure_mcp.hooks import _atomic_json


def _settings(path):
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(value, dict) or not isinstance(value.get("mcpServers", {}), dict):
        raise ValueError("Antigravity configuration must contain an mcpServers object.")
    return value


def _record(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or type(value.get("had_entry")) is not bool
        or not isinstance(value.get("installed"), dict)
        or "original" not in value
    ):
        raise ValueError("Invalid Antigravity installation record.")
    return value


def configure_antigravity(path: Path, install=True):
    """Back up once, preserve other servers, and restore only our owned entry."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record_path = path.with_name(path.name + ".secure-mcp.json")
    backup = path.with_name(path.name + ".secure-mcp.bak")
    with session_file_lock(path):
        settings = _settings(path)
        servers = settings.get("mcpServers", {})
        record = _record(record_path) if record_path.exists() else None
        if record is not None and servers.get("secure-mcp") != record["installed"]:
            raise ValueError(
                "SecureMCP registration changed; merge it before reinstalling/removing."
            )
        if not install and record is None:
            return None
        original_bytes = path.read_bytes() if path.exists() else None
        previous_record = record_path.read_bytes() if record_path.exists() else None
        if install:
            installed = {
                "command": sys.executable,
                "args": ["-m", "secure_mcp", "serve"],
            }
            if record is None:
                record = {
                    "had_entry": "secure-mcp" in servers,
                    "original": servers.get("secure-mcp"),
                    "installed": installed,
                }
                if original_bytes is not None:
                    atomic_bytes(backup, original_bytes)
            else:
                record["installed"] = installed
            servers["secure-mcp"] = installed
        else:
            assert record is not None
            if record["had_entry"]:
                servers["secure-mcp"] = record["original"]
            else:
                servers.pop("secure-mcp", None)
        settings["mcpServers"] = servers
        try:
            if install:
                _atomic_json(record_path, record)
            _atomic_json(path, settings)
            if not install:
                record_path.unlink()
        except OSError:
            if original_bytes is None:
                path.unlink(missing_ok=True)
            else:
                atomic_bytes(path, original_bytes)
            if previous_record is None:
                record_path.unlink(missing_ok=True)
            else:
                atomic_bytes(record_path, previous_record)
            raise
    return backup if backup.exists() else None


def antigravity_status(path: Path):
    settings = _settings(path)
    record_path = path.with_name(path.name + ".secure-mcp.json")
    record = _record(record_path) if record_path.exists() else None
    return {
        "agent": "antigravity",
        "settings": str(path),
        "ready": record is not None
        and settings.get("mcpServers", {}).get("secure-mcp") == record["installed"],
    }

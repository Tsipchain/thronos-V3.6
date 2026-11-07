"""Scanner probes cannot poison access to public pages through a shared proxy."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def _scanner_hooks():
    source = Path(__file__).resolve().parents[1] / "server_ext.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_is_probe_path", "_block_scanners"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in {
                "_PHP_PROBE_SUFFIXES", "_PHP_PROBE_KEYWORDS",
            }
            for target in node.targets
        ):
            nodes.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
    assert len(nodes) == 4

    def reject(status):
        raise PermissionError(status)

    request = SimpleNamespace(path="/", remote_addr="172.68.1.1", headers={})
    ns = {"_req": request, "_abort": reject}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns["_block_scanners"], request


def test_probe_paths_still_rejected():
    guard, request = _scanner_hooks()
    for path in ("/wp-login.php", "/.env", "/shell.cgi"):
        request.path = path
        with pytest.raises(PermissionError, match="403"):
            guard()


def test_repeated_probes_do_not_block_other_pages_or_users():
    guard, request = _scanner_hooks()
    request.headers = {"X-Forwarded-For": "192.0.2.42"}
    for _ in range(12):
        request.path = "/wp-login.php"
        with pytest.raises(PermissionError, match="403"):
            guard()
    for path in ("/", "/earn", "/api/earn/ads", "/api/token/prices"):
        request.path = path
        assert guard() is None
    request.remote_addr = "198.51.100.8"
    request.path = "/earn"
    assert guard() is None

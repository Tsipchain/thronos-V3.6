"""The old THR pool route must never debit a wallet from caller-supplied IDs."""

import ast
from pathlib import Path


def test_legacy_thr_deposit_requires_verified_wallet_intent():
    source = (Path(__file__).resolve().parents[1] / "server.py").read_text()
    tree = ast.parse(source)
    route = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "api_pools_thr_deposit"
    )
    route.decorator_list = []
    namespace = {"jsonify": lambda **data: data}
    exec(compile(ast.Module(body=[route], type_ignores=[]), "server.py", "exec"), namespace)
    payload, status = namespace["api_pools_thr_deposit"]()
    assert status == 409
    assert payload == {"ok": False, "error": "signed_wallet_intent_required"}
    # Any reference to the file ledger or pool positions in this handler
    # would mean an alternate, unsafe route survived the migration.
    names = {node.id for node in ast.walk(route) if isinstance(node, ast.Name)}
    assert not names.intersection({"LEDGER_FILE", "_load_pool_ledger", "_save_pool_positions"})

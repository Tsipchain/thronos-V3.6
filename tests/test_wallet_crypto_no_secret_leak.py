"""
Regression test — wallet_crypto.py must never print or log private keys,
mnemonics, seed phrases, or signing material.

Scans the source file for dangerous patterns and fails if any are found.
"""
import ast
import textwrap
from pathlib import Path

import pytest

_WALLET_CRYPTO_PATH = Path(__file__).resolve().parent.parent / "wallet_crypto.py"

_FORBIDDEN_ATTRS = {
    "private_key",
    "mnemonic",
    "seed_phrase",
    "seed",
    "signing_key",
    "secret_key",
}

_FORBIDDEN_LITERALS = {
    "private_key",
    "private key",
    "mnemonic",
    "seed_phrase",
    "seed phrase",
    "signing_key",
    "secret_key",
}

_SINK_NAMES = {"print", "logging", "log"}


def _collect_dangerous_calls(source: str) -> list[str]:
    """Find print/logging calls that reference forbidden secret attributes."""
    violations: list[str] = []
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id in _SINK_NAMES:
                    func_name = f"{node.func.value.id}.{node.func.attr}"

        is_print = func_name == "print"
        is_log = any(
            func_name.startswith(f"{s}.") for s in _SINK_NAMES
        )

        if not (is_print or is_log):
            continue

        call_source = ast.dump(node)
        for arg in ast.walk(node):
            if isinstance(arg, ast.Attribute) and arg.attr in _FORBIDDEN_ATTRS:
                violations.append(
                    f"line {node.lineno}: {func_name}() references .{arg.attr}"
                )
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                val_lower = arg.value.lower()
                for lit in _FORBIDDEN_LITERALS:
                    if lit in val_lower:
                        violations.append(
                            f"line {node.lineno}: {func_name}() contains "
                            f"string literal '{arg.value[:40]}'"
                        )

    return violations


def test_wallet_crypto_source_exists():
    """wallet_crypto.py must be present."""
    assert _WALLET_CRYPTO_PATH.exists(), f"missing: {_WALLET_CRYPTO_PATH}"


def test_no_private_key_in_print_or_log():
    """No print() or logging call may reference private_key, mnemonic, or seed."""
    source = _WALLET_CRYPTO_PATH.read_text()
    violations = _collect_dangerous_calls(source)
    assert violations == [], (
        "wallet_crypto.py leaks secret material:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_main_prints_only_address():
    """The main() CLI path must print only the public address."""
    source = _WALLET_CRYPTO_PATH.read_text()
    tree = ast.parse(source)

    main_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_func = node
            break

    assert main_func is not None, "main() function not found"

    for child in ast.walk(main_func):
        if isinstance(child, ast.Attribute) and child.attr in _FORBIDDEN_ATTRS:
            pytest.fail(
                f"main() references .{child.attr} at line {child.lineno} — "
                "only public address output is allowed"
            )


def test_no_authorization_header_logged():
    """No logging call may output raw Authorization header values."""
    source = _WALLET_CRYPTO_PATH.read_text()
    source_lower = source.lower()
    for pattern in ("authorization", "bearer"):
        for sink in ("print(", "log."):
            lines = source.splitlines()
            for i, line in enumerate(lines, 1):
                ll = line.lower()
                if sink in ll and pattern in ll:
                    pytest.fail(
                        f"line {i}: potential Authorization header leak in {sink}... call"
                    )

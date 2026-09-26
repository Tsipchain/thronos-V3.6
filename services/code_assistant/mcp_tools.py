"""MCP-compatible tool definitions for the Code Assistant.

Each tool has:
  - A schema (for the LLM to know how to call it)
  - An executor (runs the tool and returns the result)

Tools: file_read, file_write, file_search, code_grep, git_status,
       git_diff, git_commit, git_log, run_command, list_directory.
"""

import os
import json
import glob
import subprocess
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_ROOT = os.getenv("CODE_ASSISTANT_WORKSPACE", os.path.join(_PROJECT_DIR, "data", "workspace"))
MAX_FILE_SIZE = 1_000_000  # 1MB read limit
MAX_OUTPUT = 50_000  # 50KB command output limit

BLOCKED_COMMANDS = {
    "rm -rf /", "mkfs", "dd if=", ":(){", "shutdown",
    "reboot", "halt", "poweroff", "init 0", "init 6",
}


def _safe_path(path: str) -> str:
    """Resolve path within workspace to prevent directory traversal."""
    resolved = os.path.normpath(os.path.join(WORKSPACE_ROOT, path))
    if not resolved.startswith(os.path.normpath(WORKSPACE_ROOT)):
        raise ValueError(f"Path escapes workspace: {path}")
    return resolved


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated, {len(text)} total bytes]"
    return text


# --- Tool Schemas (Ollama/OpenAI function-calling format) ---

TOOL_SCHEMAS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a file's contents. Supports offset/limit for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "offset": {"type": "integer", "description": "Start line (0-based)", "default": 0},
                    "limit": {"type": "integer", "description": "Max lines to read", "default": 200},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write content to a file (creates or overwrites).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_edit",
            "description": "Replace a specific string in a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "old_string": {"type": "string", "description": "Exact text to find and replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Find files matching a glob pattern in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_grep",
            "description": "Search for a regex pattern in files. Returns matching lines with file paths and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                    "file_pattern": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to workspace", "default": "."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status of the workspace repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff (staged and unstaged changes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "Show only staged changes", "default": false},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of commits to show", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage files and create a git commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files to stage (relative paths). Empty = stage all changed files.",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the workspace. Use for: running tests, linting, building, installing packages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                },
                "required": ["command"],
            },
        },
    },
]


# --- Tool Executors ---

def file_read(path: str, offset: int = 0, limit: int = 200) -> Dict[str, Any]:
    full_path = _safe_path(path)
    if not os.path.isfile(full_path):
        return {"error": f"File not found: {path}"}
    if os.path.getsize(full_path) > MAX_FILE_SIZE:
        return {"error": f"File too large (>{MAX_FILE_SIZE} bytes). Use offset/limit."}
    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    selected = lines[offset:offset + limit]
    numbered = [f"{offset + i + 1}\t{line}" for i, line in enumerate(selected)]
    return {
        "content": "".join(numbered),
        "total_lines": len(lines),
        "showing": f"{offset + 1}-{min(offset + limit, len(lines))}",
    }


def file_write(path: str, content: str) -> Dict[str, Any]:
    full_path = _safe_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"written": path, "bytes": len(content.encode("utf-8"))}


def file_edit(path: str, old_string: str, new_string: str) -> Dict[str, Any]:
    full_path = _safe_path(path)
    if not os.path.isfile(full_path):
        return {"error": f"File not found: {path}"}
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(old_string)
    if count == 0:
        return {"error": "old_string not found in file"}
    if count > 1:
        return {"error": f"old_string found {count} times — must be unique. Add more context."}
    new_content = content.replace(old_string, new_string, 1)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return {"edited": path, "replacements": 1}


def file_search(pattern: str) -> Dict[str, Any]:
    matches = sorted(glob.glob(os.path.join(WORKSPACE_ROOT, pattern), recursive=True))
    relative = [os.path.relpath(m, WORKSPACE_ROOT) for m in matches[:200]]
    return {"matches": relative, "total": len(matches)}


def code_grep(pattern: str, path: str = ".", file_pattern: Optional[str] = None) -> Dict[str, Any]:
    search_path = _safe_path(path)
    cmd = ["grep", "-rn", "--include", file_pattern or "*", "-E", pattern, search_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = _truncate(result.stdout)
        lines = output.strip().split("\n") if output.strip() else []
        relative_lines = []
        for line in lines[:100]:
            relative_lines.append(line.replace(WORKSPACE_ROOT + "/", ""))
        return {"matches": relative_lines, "count": len(lines)}
    except subprocess.TimeoutExpired:
        return {"error": "Search timed out (30s limit)"}


def list_directory(path: str = ".") -> Dict[str, Any]:
    full_path = _safe_path(path)
    if not os.path.isdir(full_path):
        return {"error": f"Not a directory: {path}"}
    entries = []
    for name in sorted(os.listdir(full_path)):
        full = os.path.join(full_path, name)
        entry = {"name": name, "type": "dir" if os.path.isdir(full) else "file"}
        if entry["type"] == "file":
            entry["size"] = os.path.getsize(full)
        entries.append(entry)
    return {"entries": entries[:500], "path": path}


def git_status() -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=WORKSPACE_ROOT, timeout=10,
        )
        return {"status": result.stdout.strip(), "clean": result.stdout.strip() == ""}
    except Exception as exc:
        return {"error": str(exc)}


def git_diff(staged: bool = False) -> Dict[str, Any]:
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE_ROOT, timeout=30)
        return {"diff": _truncate(result.stdout)}
    except Exception as exc:
        return {"error": str(exc)}


def git_log(count: int = 10) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "log", f"-{count}", "--oneline", "--graph"],
            capture_output=True, text=True, cwd=WORKSPACE_ROOT, timeout=10,
        )
        return {"log": result.stdout.strip()}
    except Exception as exc:
        return {"error": str(exc)}


def git_commit(message: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        if files:
            for f in files:
                safe = _safe_path(f)
                subprocess.run(["git", "add", safe], cwd=WORKSPACE_ROOT, timeout=10)
        else:
            subprocess.run(["git", "add", "-A"], cwd=WORKSPACE_ROOT, timeout=10)

        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, cwd=WORKSPACE_ROOT, timeout=30,
        )
        return {"output": result.stdout.strip(), "returncode": result.returncode}
    except Exception as exc:
        return {"error": str(exc)}


def run_command(command: str, timeout: int = 60) -> Dict[str, Any]:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return {"error": f"Blocked command: {blocked}"}
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=WORKSPACE_ROOT, timeout=timeout,
        )
        return {
            "stdout": _truncate(result.stdout),
            "stderr": _truncate(result.stderr),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out ({timeout}s limit)"}


# --- Tool Executor Dispatch ---

TOOL_EXECUTORS = {
    "file_read": file_read,
    "file_write": file_write,
    "file_edit": file_edit,
    "file_search": file_search,
    "code_grep": code_grep,
    "list_directory": list_directory,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "git_commit": git_commit,
    "run_command": run_command,
}


def execute_tool(name: str, arguments: dict) -> Any:
    """Execute a tool by name with the given arguments."""
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        return {"error": f"Unknown tool: {name}"}
    try:
        return executor(**arguments)
    except Exception as exc:
        return {"error": f"{name} failed: {exc}"}

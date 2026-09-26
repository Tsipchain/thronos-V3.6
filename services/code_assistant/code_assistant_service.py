"""Thronos Code Assistant Service.

Self-hosted AI coding tenant that:
  - Runs a local LLM via Ollama (no API key needed)
  - Has MCP tools for file ops, git, code search, terminal
  - Connects to any GitHub repo or local project
  - Supports multi-turn agentic coding sessions

Deployment: Railway service with GPU (24 vCPU / 24GB VRAM)
Model: Qwen2.5-Coder-32B (Q4) or any Ollama-supported model
"""

import os
import json
import uuid
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mcp_tools import TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_ROOT = os.getenv("CODE_ASSISTANT_WORKSPACE", os.path.join(_PROJECT_DIR, "data", "workspace"))
SESSIONS_DIR = os.getenv("CODE_ASSISTANT_SESSIONS", os.path.join(_PROJECT_DIR, "data", "code_sessions"))
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

SYSTEM_PROMPT = """You are Thronos Code Assistant — a self-hosted AI coding agent running on the Thronos network.

You have full access to the workspace through MCP tools:
- file_read / file_write / file_edit — read, create, and modify files
- file_search / code_grep — find files and search code
- list_directory — browse the project structure
- git_status / git_diff / git_log / git_commit — full git operations
- run_command — run tests, lint, build, install packages

Guidelines:
- Read files before editing them
- Run tests after making changes
- Write clean, well-structured code
- Commit with clear messages
- Never expose secrets or credentials
- Prefer editing existing files over creating new ones

You support all programming languages: Python, JavaScript/TypeScript, Rust, Go, Solidity, C/C++, Java, and more.
"""


class CodeSession:
    """A coding session with conversation history and workspace state."""

    def __init__(self, session_id: str, repo_url: Optional[str] = None,
                 workspace: Optional[str] = None, model: Optional[str] = None):
        self.session_id = session_id
        self.repo_url = repo_url
        self.workspace = workspace or os.path.join(WORKSPACE_ROOT, session_id)
        self.model = model
        self.messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.tool_calls: List[dict] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "repo_url": self.repo_url,
            "workspace": self.workspace,
            "model": self.model,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodeSession":
        session = cls(
            session_id=data["session_id"],
            repo_url=data.get("repo_url"),
            workspace=data.get("workspace"),
            model=data.get("model"),
        )
        session.messages = data.get("messages", [])
        session.tool_calls = data.get("tool_calls", [])
        session.created_at = data.get("created_at", session.created_at)
        session.updated_at = data.get("updated_at", session.updated_at)
        return session


class CodeAssistantService:
    """Main service for the Code Assistant tenant."""

    def __init__(self):
        self.sessions: Dict[str, CodeSession] = {}
        Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
        Path(WORKSPACE_ROOT).mkdir(parents=True, exist_ok=True)

    def _get_ollama_helper(self):
        """Lazy import to avoid circular deps at module level."""
        import importlib
        mod = importlib.import_module("ai.providers.ollama_helper")
        return mod

    def create_session(
        self,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
        model: Optional[str] = None,
        workspace_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new coding session, optionally cloning a repo."""
        session_id = f"code-{uuid.uuid4().hex[:12]}"
        workspace = workspace_path or os.path.join(WORKSPACE_ROOT, session_id)

        if repo_url:
            Path(workspace).mkdir(parents=True, exist_ok=True)
            cmd = ["git", "clone", "--depth", "50"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([repo_url, workspace])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return {"error": f"Clone failed: {result.stderr}", "session_id": session_id}
        else:
            Path(workspace).mkdir(parents=True, exist_ok=True)

        session = CodeSession(
            session_id=session_id,
            repo_url=repo_url,
            workspace=workspace,
            model=model,
        )
        self.sessions[session_id] = session
        self._save_session(session)

        return {
            "session_id": session_id,
            "workspace": workspace,
            "repo_url": repo_url,
            "model": model or "default",
            "status": "ready",
        }

    def send_message(
        self,
        session_id: str,
        message: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message to the coding assistant and get a response.

        The assistant may call tools (file read/write, git, grep, etc.)
        in a multi-turn loop until it has a final answer.
        """
        session = self._load_session(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}

        os.environ["CODE_ASSISTANT_WORKSPACE"] = session.workspace
        from . import mcp_tools
        mcp_tools.WORKSPACE_ROOT = session.workspace

        session.messages.append({"role": "user", "content": message})

        ollama = self._get_ollama_helper()
        use_model = model or session.model

        result = ollama.generate_with_tools(
            messages=session.messages,
            tools=TOOL_SCHEMAS,
            model=use_model,
            tool_executor=execute_tool,
        )

        assistant_content = result.get("content", "")
        tool_calls_made = result.get("tool_calls", [])

        session.messages.append({"role": "assistant", "content": assistant_content})
        session.tool_calls.extend(tool_calls_made)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_session(session)

        return {
            "session_id": session_id,
            "response": assistant_content,
            "tool_calls_count": len(tool_calls_made),
            "model": result.get("model", ""),
            "provider": "ollama",
        }

    def list_sessions(self) -> List[dict]:
        """List all coding sessions."""
        sessions = []
        sessions_path = Path(SESSIONS_DIR)
        for f in sorted(sessions_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(f, "r") as fp:
                    data = json.load(fp)
                sessions.append({
                    "session_id": data["session_id"],
                    "repo_url": data.get("repo_url"),
                    "model": data.get("model"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception:
                continue
        return sessions

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get full session details."""
        session = self._load_session(session_id)
        if session:
            return session.to_dict()
        return None

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete a session and its workspace."""
        session = self._load_session(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}

        session_file = Path(SESSIONS_DIR) / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()

        self.sessions.pop(session_id, None)
        return {"deleted": session_id}

    def get_model_status(self) -> Dict[str, Any]:
        """Check Ollama status and available models."""
        ollama = self._get_ollama_helper()
        health = ollama.health_check()
        return {
            "ollama_url": OLLAMA_BASE,
            "healthy": health.get("healthy", False),
            "available_models": health.get("models", []),
            "error": health.get("error"),
        }

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """Pull a model from Ollama registry."""
        ollama = self._get_ollama_helper()
        return ollama.pull_model(model_name)

    def _save_session(self, session: CodeSession) -> None:
        path = Path(SESSIONS_DIR) / f"{session.session_id}.json"
        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

    def _load_session(self, session_id: str) -> Optional[CodeSession]:
        if session_id in self.sessions:
            return self.sessions[session_id]
        path = Path(SESSIONS_DIR) / f"{session_id}.json"
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
            session = CodeSession.from_dict(data)
            self.sessions[session_id] = session
            return session
        return None

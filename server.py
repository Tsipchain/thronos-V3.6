# server.py  (ThronosChain — Full, unified, quorum-enabled)
# - pledge + secure PDF (AES + QR + stego)
#
# Enable postponed evaluation for type hints used in helper functions.
from __future__ import annotations
#
# --- Imports ---
# - wallet + mining rewards
# - data volume (/app/data)
# - whitelist για free pledges
# - ασφαλές THR send με auth_secret (seed) ανά THR address
# - migration για ήδη υπάρχοντα pledges -> send_seed / send_auth_hash
# - last_block.json για σταθερό viewer/home status
# - recovery flow via steganography
# - Dynamic Difficulty & Halving
# - AI Agent Auto-Registration
# - Token Chart & Network Stats
# - Bitcoin Bridge Watcher & IoT Nodes
# - SHA256d PoW Support
# - Quantum-Secured AI Chat
# - AI Autonomous Driving Service
# - Mempool & 80/10/10 Reward Split (V3.7)
# - Quorum Attestations (BLS/MuSig2 placeholder) + aggregator job (V2.9)
# - AI Knowledge Blocks: ai_block_log.json -> mempool -> ai_knowledge TXs (V4.0)
# - AI Architect & Multi-Model Support (V3.6 Update)
# - Dynamic Fees & Burning (V4.1)
# - Swap / DeFi Interface (V4.2)
# - IoT Parking State (V4.3)
# - Crypto Hunters P2E (V4.4)
# - Real Fiat Gateway (Stripe + Bank Withdrawals) (V5.0)
# - Admin Withdrawal Panel (V5.1)

import os, json, time, hashlib, logging, secrets, random, uuid, zipfile, struct, binascii
from collections import Counter
from decimal import Decimal, ROUND_DOWN
import qrcode
import io
import numpy as np
import wave
from datetime import datetime
from typing import Any
from PIL import Image

try:
    import anthropic
except Exception:
    anthropic = None

import os
import re
import mimetypes
import json
import requests
from flask import Flask, request, jsonify, send_from_directory, render_template, url_for, send_file

try:
    from flask_cors import CORS
except ImportError:  # Railway ή env χωρίς flask_cors
    def CORS(app, *args, **kwargs):
        # απλό no-op fallback ώστε ο server να μην σκάει
        return app

from werkzeug.middleware.proxy_fix import ProxyFix

# CRITICAL FIX #1: Import secure_filename with fallback
try:
    from werkzeug.utils import secure_filename
except ImportError:
    # Fallback sanitizer if werkzeug doesn't have secure_filename
    def secure_filename(filename):
        """Minimal filename sanitizer - replace non-alphanumeric with underscore"""
        if not filename:
            return "unnamed"
        # Keep extension, sanitize base name
        import re
        name, ext = os.path.splitext(filename)
        name = re.sub(r'[^a-zA-Z0-9_.-]', '_', name)[:100]  # Max 100 chars
        ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)[:10]  # Max 10 chars for extension
        return (name + ext) if name else "unnamed" + ext

from apscheduler.schedulers.background import BackgroundScheduler

import os
import json
import uuid
from llm_registry import AI_MODEL_REGISTRY, get_model_for_provider, get_default_model_for_mode, get_provider_status
from ai_models_config import base_model_config
# CRITICAL FIX #6: Import compute_model_stats from ai_interaction_ledger
from ai_interaction_ledger import compute_model_stats

app = Flask(__name__)
CORS(app)

# FIX 9: Redirect old SESSIONS_DIR to volume-backed AI_SESSIONS_DIR (defined later at line 550)
# This ensures all sessions persist across deployments
SESSIONS_DIR = None  # Will be set after DATA_DIR is defined


@app.route('/chat_sessions', methods=['GET'])
def chat_sessions():
    try:
        sessions = []
        for filename in os.listdir(SESSIONS_DIR):
            if filename.endswith(".json"):
                sessions.append(filename.replace(".json", ""))
        return jsonify({"sessions": sessions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    session_id = data.get("session_id", str(uuid.uuid4()))
    user_message = data.get("message", "")
    provider = data.get("provider", "gpt")
    mode = data.get("mode", "chat")
    credits = int(data.get("credits", 0))

    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")

    try:
        if not os.path.exists(session_file):
            with open(session_file, "w") as f:
                json.dump({"messages": []}, f)

        with open(session_file, "r") as f:
            session_data = json.load(f)

        session_data["messages"].append({"role": "user", "content": user_message})

        model = get_model_for_provider(provider, mode) or get_default_model_for_mode(mode)
        if not model:
            return jsonify({"error": "No model available for this provider/mode."}), 400

        ai_response = f"Simulated response from {model} to: {user_message}"  # Placeholder
        session_data["messages"].append({"role": "assistant", "content": ai_response})

        with open(session_file, "w") as f:
            json.dump(session_data, f)

        return jsonify({
            "session_id": session_id,
            "messages": session_data["messages"],
            "model": model
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/load_history/<session_id>', methods=['GET'])
def load_history(session_id):
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(session_file):
        return jsonify({"messages": []})
    try:
        with open(session_file, "r") as f:
            session_data = json.load(f)
        return jsonify({"messages": session_data.get("messages", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    return send_from_directory("static", filename)

if __name__ == '__main__':
    app.run(debug=True)

## ----------------------------------------
# Optional EVM / DEX routes (wallet, swaps, liquidity)
# ----------------------------------------
try:
    # από το thronos-V3.6: όλα τα wallet / swaps / pools κλπ.
    from evm_api_v3 import register_evm_routes
except ImportError:
    register_evm_routes = None

try:
    from evm_api_v3 import register_evm_routes
except ImportError:
    register_evm_routes = None

try:
    from own_api_v1 import register_own_routes
except ImportError:
    register_own_routes = None

# Register own routes (doesn't need DATA_DIR)
if register_own_routes is not None:
    register_own_routes(app)

# Note: EVM route registration happens later after DATA_DIR and other variables are defined

# Optional Phantom + quorum imports - τυλιγμένα σε try ώστε να bootάρει το app
try:
    from phantom_gateway_mainnet import get_btc_txns
    from secure_pledge_embed import create_secure_pdf_contract
    from phantom_decode import decode_payload_from_image
    from quorum_crypto import aggregate as qc_aggregate, verify as qc_verify
except ImportError as e:
    print("CRITICAL IMPORT ERROR:", e)

    # Fallback mocks για να μη τρώμε 500άρια στο boot
    def get_btc_txns(addr, txid):
        return []

    def create_secure_pdf_contract(*args, **kwargs):
        # placeholder όταν λείπει το πραγματικό module
        return "error.pdf"

    def decode_payload_from_image(*args, **kwargs):
        return None

    def qc_aggregate(*args, **kwargs):
        return None

    def qc_verify(*args, **kwargs):
        return False

from llm_registry import AI_MODEL_REGISTRY, get_default_model_for_mode
from ai_agent_service import ThronosAI, call_llm, _resolve_model

# Optional Phantom + quorum imports - wrapped in try so app still boots if missing
from llm_registry import AI_MODEL_REGISTRY, get_default_model_for_mode
from ai_agent_service import ThronosAI, call_llm, _resolve_model

try:
    from phantom_gateway_mainnet import get_btc_txns
    from secure_pledge_embed import create_secure_pdf_contract
    from phantom_decode import decode_payload_from_image
    from quorum_crypto import aggregate as qc_aggregate, verify as qc_verify
except ImportError as e:
    # Log but do not crash the node – fall back to no-op implementations
    print("CRITICAL IMPORT ERROR:", e)

    def get_btc_txns(addr, txid):
        return []

    def create_secure_pdf_contract(*args, **kwargs):
        # placeholder filename so the rest of the flow can continue
        return "error.pdf"

    def decode_payload_from_image(*args, **kwargs):
        return None

    def qc_aggregate(*args, **kwargs):
        return None

    def qc_verify(*args, **kwargs):
        return False



import traceback
import traceback as _traceback



# ─── CONFIG ────────────────────────────────────────
app = Flask(__name__)


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
# ─── EVM INTEGRATION ────────────────────────────────────────────────────


BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Unified API contract
API_BASE_PREFIX = os.getenv("API_BASE_PREFIX", "/api")
APP_VERSION     = os.getenv("APP_VERSION", "v3.6")

AI_LOG_API_KEY = os.getenv("AI_LOG_API_KEY", os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW"))

DATA_DIR   = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

# Unified media root (persists on Railway volume)
MEDIA_DIR = os.path.join(DATA_DIR, "media")
TOKEN_LOGOS_DIR = os.path.join(MEDIA_DIR, "token_logos")
NFT_IMAGES_DIR = os.path.join(MEDIA_DIR, "nft_images")
COURSE_MEDIA_DIR = os.path.join(MEDIA_DIR, "courses")
COURSE_COVERS_DIR = os.path.join(COURSE_MEDIA_DIR, "covers")
COURSE_FILES_DIR = os.path.join(COURSE_MEDIA_DIR, "files")
MUSIC_AUDIO_DIR = os.path.join(MEDIA_DIR, "music_audio")
MUSIC_COVER_DIR = os.path.join(MEDIA_DIR, "music_covers")
L2E_ENROLLMENTS_FILE = os.path.join(DATA_DIR, "l2e_enrollments.json")

for _dir in [MEDIA_DIR, TOKEN_LOGOS_DIR, NFT_IMAGES_DIR, COURSE_MEDIA_DIR,
             COURSE_COVERS_DIR, COURSE_FILES_DIR, MUSIC_AUDIO_DIR, MUSIC_COVER_DIR]:
    os.makedirs(_dir, exist_ok=True)

# AI provider/model caches
MODEL_CATALOG: dict = {}
MODEL_CATALOG_LAST_REFRESH = 0.0
MODEL_REFRESH_INTERVAL_SECONDS = float(os.getenv("MODEL_REFRESH_INTERVAL_SECONDS", 6 * 3600))
PROVIDER_HEALTH_CACHE: dict = {}
PROVIDER_HEALTH_TTL = 300  # seconds

# Node role: "master" or "replica"
NODE_ROLE = os.getenv("NODE_ROLE", "master").lower()
MASTER_INTERNAL_URL = os.getenv("MASTER_NODE_URL", "http://localhost:5000")
# Replica external URL - used for heartbeat registration (e.g., Railway URL)
REPLICA_EXTERNAL_URL = os.getenv("REPLICA_EXTERNAL_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))

LEDGER_FILE         = os.path.join(DATA_DIR, "ledger.json")
WBTC_LEDGER_FILE    = os.path.join(DATA_DIR, "wbtc_ledger.json")
CHAIN_FILE          = os.path.join(DATA_DIR, "phantom_tx_chain.json")
PLEDGE_CHAIN        = os.path.join(DATA_DIR, "pledge_chain.json")
LAST_BLOCK_FILE     = os.path.join(DATA_DIR, "last_block.json")
WHITELIST_FILE      = os.path.join(DATA_DIR, "free_pledge_whitelist.json")
AI_CREDS_FILE       = os.path.join(DATA_DIR, "ai_agent_credentials.json")
AI_BLOCK_LOG_FILE   = os.path.join(DATA_DIR, "ai_block_log.json")
AI_INTERACTIONS_FILE = os.path.join(DATA_DIR, "ai_interactions.jsonl")
WATCHER_LEDGER_FILE = os.path.join(DATA_DIR, "watcher_ledger.json")
IOT_DATA_FILE       = os.path.join(DATA_DIR, "iot_data.json")
IOT_PARKING_FILE    = os.path.join(DATA_DIR, "iot_parking.json")
MEMPOOL_FILE        = os.path.join(DATA_DIR, "mempool.json")
ATTEST_STORE_FILE   = os.path.join(DATA_DIR, "attest_store.json")
WITHDRAWALS_FILE    = os.path.join(DATA_DIR, "withdrawals.json") # NEW
VOTING_FILE         = os.path.join(DATA_DIR, "voting.json") # Feature voting for Crypto Hunters
PEERS_FILE          = os.path.join(DATA_DIR, "active_peers.json") # Heartbeat tracking

# Active peers tracking (for replicas heartbeating to master)
PEER_TTL_SECONDS = 60  # Peers expire after 60 seconds without heartbeat
active_peers = {}  # {peer_id: {"last_seen": timestamp, "url": replica_url}}

# AI commerce
AI_PACKS_FILE       = os.path.join(DATA_DIR, "ai_packs.json")
AI_CREDITS_FILE     = os.path.join(DATA_DIR, "ai_credits.json")

# Register optional EVM routes (if module exists)
if register_evm_routes is not None:
    try:
        register_evm_routes(app, DATA_DIR, LEDGER_FILE, CHAIN_FILE, PLEDGE_CHAIN)  # type: ignore
        print('[EVM] routes registered')
    except Exception as _e:
        print(f'[EVM] routes not registered: {_e}')

# --------------------------------------------------------------------------
# AI demo usage tracking
#
# When a user chats with the AI without providing a THR wallet address, the
# system treats the conversation as a free demo.  In order to prevent abuse
# and runaway resource consumption, the server tracks how many free messages
# have been consumed per session.  Once the free limit is reached, further
# requests are denied until a wallet is supplied.  The counters are stored
# in ``AI_FREE_USAGE_FILE`` and keyed by the session ID supplied by the
# --- Guest access (no wallet) ---
AI_FREE_MESSAGES_LIMIT = int(os.getenv("AI_FREE_MESSAGES_LIMIT", "5"))
GUEST_MAX_FREE_MESSAGES = int(os.getenv("GUEST_MAX_FREE_MESSAGES", str(AI_FREE_MESSAGES_LIMIT)))
GUEST_MAX_FREE_SESSIONS = int(os.getenv("GUEST_MAX_FREE_SESSIONS", "1"))  # keep it simple
GUEST_COOKIE_NAME = "thr_guest_id"
GUEST_TTL_SECONDS = int(os.getenv("GUEST_TTL_SECONDS", str(7*24*3600)))  # 7 days

GUEST_STATE_FILE = os.path.join(DATA_DIR, "guest_state.json")

def _now_ts() -> int:
    return int(time.time())

def get_or_set_guest_id():
    gid = request.cookies.get(GUEST_COOKIE_NAME)
    if not gid:
        gid = f"GST{uuid.uuid4().hex[:16]}"
    return gid

def load_guest_state():
    try:
        with open(GUEST_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_guest_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(GUEST_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def guest_state_get(gid: str) -> dict:
    state = load_guest_state()
    g = state.get(gid, {})
    # expire
    if g.get("expires_at") and g["expires_at"] < _now_ts():
        state.pop(gid, None)
        save_guest_state(state)
        return {}
    return g

def guest_state_set(gid: str, g: dict):
    state = load_guest_state()
    g["expires_at"] = _now_ts() + GUEST_TTL_SECONDS
    state[gid] = g
    save_guest_state(state)

def guest_decrement_free_messages(gid: str) -> int:
    g = guest_state_get(gid)
    used = int(g.get("used_messages", 0))
    used += 1
    g["used_messages"] = used
    guest_state_set(gid, g)
    remaining = max(0, GUEST_MAX_FREE_MESSAGES - used)
    return remaining

def guest_remaining_free_messages(gid: str) -> int:
    g = guest_state_get(gid)
    used = int(g.get("used_messages", 0))
    return max(0, GUEST_MAX_FREE_MESSAGES - used)

# --- Chat file uploads ---
AI_UPLOADS_DIR = os.path.join(DATA_DIR, "ai_uploads")
# Use a single index file for all AI uploads.  Both upload and download
# endpoints read/write this index.  This avoids having separate
# ai_uploads/index.json and ai_files_index.json that get out of sync.  The
# index stores metadata keyed by file_id and includes the absolute path of
# the stored file.  See store_uploaded_file() for details.
AI_UPLOADS_INDEX = os.path.join(DATA_DIR, "ai_files_index.json")

def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:128] or "file"

def load_upload_index() -> dict:
    """
    Load the unified AI upload index.  The index is stored in
    ``AI_UPLOADS_INDEX`` (data/ai_files_index.json) and contains
    metadata for each uploaded file keyed by file_id.  If the index
    does not exist or is corrupt, return an empty dict.
    """
    try:
        with open(AI_UPLOADS_INDEX, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_upload_index(index: dict) -> None:
    """
    Persist the unified AI upload index to ``AI_UPLOADS_INDEX``.  The
    index directory is created if it does not exist.  This helper is
    used by ``store_uploaded_file`` to record new uploads.
    """
    os.makedirs(os.path.dirname(AI_UPLOADS_INDEX), exist_ok=True)
    with open(AI_UPLOADS_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

def store_uploaded_file(file_storage, owner_wallet: str | None, session_id: str | None, owner_guest: str | None):
    os.makedirs(AI_UPLOADS_DIR, exist_ok=True)
    file_id = f"F{uuid.uuid4().hex}"
    fname = _safe_filename(file_storage.filename)
    path = os.path.join(AI_UPLOADS_DIR, f"{file_id}__{fname}")
    file_storage.save(path)
    meta = {
        "file_id": file_id,
        "filename": fname,
        "path": path,
        "size": os.path.getsize(path),
        "content_type": file_storage.mimetype,
        "wallet": owner_wallet,
        "guest_id": owner_guest,
        "session_id": session_id,
        "created_at": _now_ts()
    }
    idx = load_upload_index()
    idx[file_id] = meta
    save_upload_index(idx)
    return meta

def read_text_file_for_prompt(path: str, max_bytes: int = 200_000) -> str:
    """
    Read file content for AI prompt. Supports:
    - Text files (direct content)
    - PDF files (text extraction)
    - Code files (with syntax hints)
    - Other files (metadata description)
    """
    import mimetypes

    try:
        ext = os.path.splitext(path)[1].lower()
        mime, _ = mimetypes.guess_type(path)

        # Text-based files (code, txt, json, etc.)
        text_exts = {'.txt', '.md', '.json', '.xml', '.csv', '.py', '.js', '.ts',
                     '.html', '.css', '.sql', '.yaml', '.yml', '.sh', '.bat',
                     '.c', '.cpp', '.h', '.java', '.go', '.rs', '.rb', '.php',
                     '.sol', '.toml', '.ini', '.cfg', '.log', '.env'}

        if ext in text_exts or (mime and mime.startswith('text/')):
            with open(path, "rb") as f:
                data = f.read(max_bytes + 1)
            if len(data) > max_bytes:
                return f"[File truncated - showing first {max_bytes} bytes]\n" + data[:max_bytes].decode("utf-8", errors="replace")
            content = data.decode("utf-8", errors="replace")
            # Add syntax hint for code files
            lang_hint = ext[1:] if ext else ""
            if lang_hint in ['py', 'js', 'ts', 'sol', 'java', 'go', 'rs']:
                return f"```{lang_hint}\n{content}\n```"
            return content

        # PDF files - try to extract text
        if ext == '.pdf':
            try:
                import PyPDF2
                with open(path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text_parts = []
                    for page_num, page in enumerate(reader.pages[:20]):  # Max 20 pages
                        text_parts.append(f"--- Page {page_num + 1} ---\n{page.extract_text()}")
                    content = "\n".join(text_parts)
                    if len(content) > max_bytes:
                        content = content[:max_bytes] + "\n[PDF content truncated]"
                    return f"[PDF Document - {len(reader.pages)} pages]\n{content}"
            except ImportError:
                return f"[PDF file: {os.path.basename(path)} - PDF text extraction not available. File size: {os.path.getsize(path)} bytes]"
            except Exception as e:
                return f"[PDF file: {os.path.basename(path)} - Could not extract text: {str(e)[:100]}]"

        # Image files - provide metadata description
        img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
        if ext in img_exts or (mime and mime.startswith('image/')):
            size = os.path.getsize(path)
            try:
                from PIL import Image
                with Image.open(path) as img:
                    return f"[Image file: {os.path.basename(path)} | Format: {img.format} | Size: {img.size[0]}x{img.size[1]} | Mode: {img.mode} | File size: {size} bytes]\n[Note: Image content cannot be displayed in text. Please describe what you want to do with this image.]"
            except:
                return f"[Image file: {os.path.basename(path)} | Size: {size} bytes]\n[Note: Image content available but cannot be displayed in text prompt.]"

        # Binary/other files - provide metadata
        size = os.path.getsize(path)
        return f"[Binary file: {os.path.basename(path)} | MIME type: {mime or 'unknown'} | Size: {size} bytes]\n[Note: Binary content cannot be directly included in prompt. Please specify what you want to do with this file.]"

    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        return f"[Unable to read file: {str(e)[:100]}]"
# client.  If no session_id is provided, the counter falls back to the key
# 'default'.  Set ``AI_FREE_MESSAGES_LIMIT`` via an environment variable to
# control how many free messages are allowed.

AI_FREE_USAGE_FILE  = os.path.join(DATA_DIR, "ai_free_usage.json")

# AI extra storage
AI_FILES_DIR   = os.path.join(DATA_DIR, "ai_files")
AI_CORPUS_FILE = os.path.join(DATA_DIR, "ai_offline_corpus.json")
os.makedirs(AI_FILES_DIR, exist_ok=True)

# NEW: αποθήκευση sessions (λίστα συνομιλιών)
AI_SESSIONS_FILE = os.path.join(DATA_DIR, "ai_sessions.json")
AI_SESSIONS_DIR = os.path.join(DATA_DIR, "ai_sessions")
AI_FILES_INDEX = os.path.join(DATA_DIR, "ai_files_index.json")
os.makedirs(SESSIONS_DIR, exist_ok=True)
# FIX 9: Set SESSIONS_DIR to point to volume-backed AI_SESSIONS_DIR
# This ensures all chat sessions persist across Railway deploys

SESSIONS_DIR = AI_SESSIONS_DIR

ADMIN_SECRET   = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")

BTC_RECEIVER  = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"
MIN_AMOUNT    = 0.00001

CONTRACTS_DIR = os.path.join(DATA_DIR, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

# Ensure the session transcripts directory exists for per-session message files
os.makedirs(AI_SESSIONS_DIR, exist_ok=True)

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- Dynamic Fee Config ---
FEE_RATE = 0.005  # 0.5% burn rate
MIN_FEE  = 0.001  # Minimum fee in THR

# --- Mining Config ---
INITIAL_TARGET    = 2 ** 236         # 5 hex zeros (20 bits)
TARGET_BLOCK_TIME = 60               # seconds
RETARGET_INTERVAL = 10               # blocks

AI_WALLET_ADDRESS = os.getenv("THR_AI_AGENT_WALLET", "THR_AI_AGENT_WALLET_V1")
BURN_ADDRESS      = "0x0"
SWAP_POOL_ADDRESS = "THR_SWAP_POOL_V1"
GAME_POOL_ADDRESS = "THR_CRYPTO_HUNTERS_POOL"
GAME_PANEL_URL    = os.getenv("GAME_PANEL_URL", "/game")  # Crypto Hunters admin panel URL
GATEWAY_ADDRESS   = "THR_FIAT_GATEWAY_V1"

# FIX 8: Initialize billing module (clean separation: Chat=credits, Architect=THR)
import billing
billing.init_billing(DATA_DIR, LEDGER_FILE, CHAIN_FILE, AI_CREDITS_FILE, AI_WALLET_ADDRESS)

# --- Learn‑to‑Earn Token Config ---
#
# A separate ledger is maintained for the Learn‑to‑Earn (L2E) token.  This
# token is minted as a reward for students who complete coursework and can
# be freely transferred between addresses.  A dedicated admin endpoint is
# provided to mint L2E tokens, analogous to the THR mint endpoint used by
# the BTC bridge.  The L2E ledger is persisted in ``l2e_ledger.json``
# under ``DATA_DIR``.  Initial balances are empty unless minted or
# transferred.

L2E_LEDGER_FILE = os.path.join(DATA_DIR, "l2e_ledger.json")

# Courses registry for Learn‑to‑Earn
COURSES_FILE = os.path.join(DATA_DIR, "courses.json")

# --- P2P Networking Config ---
#
# A simple peer registry is stored in ``peers.json`` under ``DATA_DIR``.  Each entry
# is expected to be the base URL of a Thronos node (e.g. ``http://ip:port``).
# These peers are used for broadcasting new transactions and blocks.  Peers can
# be added via the ``/api/v1/peers`` POST endpoint.  Keeping the list in a
# JSON file allows nodes to persist known peers across restarts without
# introducing additional dependencies.

PEERS_FILE = os.path.join(DATA_DIR, "peers.json")

# --- Tokens & DeFi Config (New for V3.8) ---
#
# To support community‑issued meme coins and basic automated market maker (AMM)
# pools, we maintain registries for tokens and liquidity pools.  Each token
# has an entry in ``tokens.json`` with its symbol, name, total supply,
# decimals and owner.  Balances for each token are stored in
# ``token_balances.json`` keyed by token symbol and address.  Pools are
# recorded in ``pools.json``, storing reserves and provider shares for each
# pair.  These data structures are intentionally simple and serve as a
# proof‑of‑concept for a more sophisticated DeFi layer in future releases.

TOKENS_FILE         = os.path.join(DATA_DIR, "tokens.json")
TOKEN_BALANCES_FILE = os.path.join(DATA_DIR, "token_balances.json")
POOLS_FILE          = os.path.join(DATA_DIR, "pools.json")

# --- Stripe Config ---
# PLEASE UPDATE THESE WITH YOUR REAL KEYS
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_live_...Tuhr") 
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_live_n7kIflBg8OTy2FJLsp80DY0M")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_PLACEHOLDER")
DOMAIN_URL = os.getenv("DOMAIN_URL", "http://localhost:3333")


# Optional Stripe dependency (server may run without it)
stripe = None
try:
    import stripe as _stripe  # type: ignore
    stripe = _stripe
except Exception:
    stripe = None

if stripe:
    stripe.api_key = STRIPE_SECRET_KEY

# Πόσα blocks "έχουν ήδη γίνει" πριν ξεκινήσει το τρέχον chain αρχείο
HEIGHT_OFFSET = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thronos")

# Security warnings for production deployments
if ADMIN_SECRET == "CHANGE_ME_NOW":
    logger.warning("⚠️  WARNING: Using default ADMIN_SECRET. Set ADMIN_SECRET environment variable for production!")
if "PLACEHOLDER" in STRIPE_WEBHOOK_SECRET or "Tuhr" in STRIPE_SECRET_KEY:
    logger.warning("⚠️  WARNING: Using placeholder Stripe keys. Update STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET for production!")

# Initialize AI
try:
    ai_agent = ThronosAI()
except Exception as e:
    print(f"AI Init Error: {e}")
    ai_agent = None

try:
    ai_scorer = ThronosAIScorer()
except Exception:
    ai_scorer = None


def _usage_from_dict(raw: dict | None) -> dict:
    if not isinstance(raw, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def _num(val):
        try:
            return int(val or 0)
        except Exception:
            return 0

    usage = {
        "input_tokens": _num(raw.get("input_tokens")),
        "output_tokens": _num(raw.get("output_tokens")),
    }
    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


def _split_system_and_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    system_prompt = None
    chat_messages: list[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            system_prompt = (system_prompt + "\n" + content) if system_prompt else content
        else:
            chat_messages.append({"role": role if role in ("user", "assistant") else "user", "content": content})
    return system_prompt, chat_messages


def call_claude(model: str, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.6) -> dict:
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        app.logger.error("Claude call blocked: missing ANTHROPIC_API_KEY")
        raise RuntimeError("Claude provider unavailable")

    system_prompt, chat_messages = _split_system_and_messages(messages)
    if not chat_messages:
        raise RuntimeError("No chat messages provided")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model or "claude-3.5-sonnet-latest",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": chat_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.Timeout:
        app.logger.error("Claude timeout", extra={"model": model})
        raise
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.error("Claude call failed", extra={"model": model, "error": str(exc)})
        raise

    if resp.status_code in (401, 403):
        app.logger.error("Claude auth failure", extra={"model": model, "status": resp.status_code})
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    text = "".join(
        [part.get("text", "") for part in data.get("content", []) if isinstance(part, dict)]
    )
    return {
        "content": text.strip(),
        "usage": _usage_from_dict(data.get("usage")),
    }


def call_openai_chat(model: str, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.6) -> dict:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        app.logger.error("OpenAI call blocked: missing OPENAI_API_KEY")
        raise RuntimeError("OpenAI provider unavailable")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or "gpt-4.1",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.Timeout:
        app.logger.error("OpenAI timeout", extra={"model": model})
        raise

    if resp.status_code in (401, 403):
        app.logger.error("OpenAI auth failure", extra={"model": model, "status": resp.status_code})
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    message = ""
    try:
        message = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    except Exception:
        message = data.get("content", "") or ""
    usage = _usage_from_dict(data.get("usage"))
    return {"content": message.strip(), "usage": usage}


def call_gemini_chat(model: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.6) -> dict:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        app.logger.error("Gemini call blocked: missing GEMINI_API_KEY/GOOGLE_API_KEY")
        raise RuntimeError("Gemini provider unavailable")

    contents = [m.get("content", "") for m in messages if isinstance(m, dict)]
    prompt = "\n\n".join(contents).strip()
    if not prompt:
        raise RuntimeError("No chat messages provided")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": api_key}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    try:
        resp = requests.post(url, params=params, json=body, timeout=30)
    except requests.Timeout:
        app.logger.error("Gemini timeout", extra={"model": model})
        raise

    if resp.status_code in (401, 403):
        app.logger.error("Gemini auth failure", extra={"model": model, "status": resp.status_code})
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    candidates = data.get("candidates", []) or []
    text = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join([p.get("text", "") for p in parts if isinstance(p, dict)])
    return {"content": text.strip(), "usage": _usage_from_dict(data.get("usage"))}


def _infer_provider(model: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    if not model:
        return "anthropic"
    ml = model.lower()
    if ml.startswith("gpt") or ml.startswith("o1") or ml.startswith("o3"):
        return "openai"
    if ml.startswith("gemini"):
        return "google"
    if ml.startswith("claude"):
        return "anthropic"
    return "anthropic"


def refresh_model_catalog(force: bool = False) -> dict:
    global MODEL_CATALOG, MODEL_CATALOG_LAST_REFRESH
    now = time.time()
    if MODEL_CATALOG and not force and now - MODEL_CATALOG_LAST_REFRESH < MODEL_REFRESH_INTERVAL_SECONDS:
        return MODEL_CATALOG

    catalog = base_model_config()
    provider_keys = {
        "openai": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
        "anthropic": bool((os.getenv("ANTHROPIC_API_KEY") or "").strip()),
        "google": bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()),
    }

    if provider_keys.get("openai"):
        try:
            res = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
                timeout=8,
            )
            if res.status_code == 200:
                data = res.json().get("data", [])
                ids = set()
                for item in data:
                    mid = item.get("id", "")
                    if any(mid.startswith(pfx) for pfx in OPENAI_MODEL_FILTER):
                        ids.add(mid)
                models = catalog.get("openai", {}).get("models", [])
                existing_ids = {m["id"] for m in models}
                for mid in sorted(ids):
                    if mid not in existing_ids:
                        models.append({"id": mid, "label": mid})
        except Exception as exc:
            app.logger.warning("OpenAI model sync failed", extra={"error": str(exc)})

    for provider, data in catalog.items():
        data["enabled"] = provider_keys.get(provider, False)

    MODEL_CATALOG = {"providers": catalog, "refreshed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    MODEL_CATALOG_LAST_REFRESH = now
    return MODEL_CATALOG


def _health_cache_ok(provider: str):
    cached = PROVIDER_HEALTH_CACHE.get(provider)
    if not cached:
        return None
    if time.time() - cached.get("ts", 0) <= PROVIDER_HEALTH_TTL:
        return cached.get("status")
    return None


def _check_provider_health(provider: str) -> str:
    cached = _health_cache_ok(provider)
    if cached:
        return cached

    status = "ok"
    try:
        if provider == "anthropic":
            call_claude("claude-3.5-sonnet-latest", [{"role": "user", "content": "ping"}], max_tokens=1, temperature=0)
        elif provider == "openai":
            call_openai_chat("gpt-4.1-mini", [{"role": "user", "content": "ping"}], max_tokens=1, temperature=0)
        elif provider == "google":
            call_gemini_chat("gemini-1.5-flash-latest", [{"role": "user", "content": "ping"}], max_tokens=1, temperature=0)
        else:
            status = "error"
    except Exception as exc:
        status = "error"
        app.logger.warning("Provider health check failed", extra={"provider": provider, "error": str(exc)})

    PROVIDER_HEALTH_CACHE[provider] = {"status": status, "ts": time.time()}
    return status


def _start_model_scheduler():
    enabled = (os.getenv("SCHEDULER_ENABLED", "true").lower() not in ("0", "false", "no"))
    if not enabled:
        app.logger.info("Model refresh scheduler disabled via SCHEDULER_ENABLED")
        return

    def _job():
        try:
            refresh_model_catalog(force=True)
        except Exception as exc:  # pragma: no cover - background job safety
            app.logger.warning("Model refresh job failed", extra={"error": str(exc)})

    scheduler = BackgroundScheduler()
    scheduler.add_job(_job, "interval", seconds=MODEL_REFRESH_INTERVAL_SECONDS, id="model_refresh", replace_existing=True)
    scheduler.start()
    app.logger.info("Background scheduler started for model catalog refresh")


# ─── HELPERS ───────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _authorized_logging_request(req) -> bool:
    key = req.headers.get("X-API-Key") or req.args.get("api_key") or ""
    return str(key) == str(AI_LOG_API_KEY)


def _load_jsonl(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return [json.loads(line) for line in lines]
    except FileNotFoundError:
        return []
    except Exception:
        try:
            return load_json(path, [])
        except Exception:
            return []


def _save_jsonl(path: str, entries: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _status_is_success(status: str) -> bool:
    status_l = (status or "").lower()
    if not status_l:
        return False
    return not any(token in status_l for token in ("error", "quota", "no_credits", "provider_error", "blocked"))


def load_ai_interactions() -> list[dict]:
    return _load_jsonl(AI_INTERACTIONS_FILE)


def save_ai_interactions(entries: list[dict]) -> None:
    _save_jsonl(AI_INTERACTIONS_FILE, entries)


def append_ai_interaction(entry: dict) -> None:
    os.makedirs(os.path.dirname(AI_INTERACTIONS_FILE), exist_ok=True)
    with open(AI_INTERACTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def record_ai_interaction(
    session_id: str | None,
    user_wallet: str | None,
    provider: str,
    model: str,
    prompt: str,
    output: str,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
    latency_ms: int,
    ai_credits_spent: float,
    feedback: dict | None = None,
    metadata: dict | None = None,
    success: bool | None = None,
    task_type: str | None = None,
    routing: dict | None = None,
    hallucination_flags: list | None = None,
    user_rating: float | None = None,
) -> dict:
    ts_ms = int(time.time() * 1000)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": ts_ms,
        "session_id": session_id,
        "user_wallet": user_wallet,
        "provider": provider,
        "model": model,
        "input_hash": _sha256_hex(prompt or ""),
        "output_hash": _sha256_hex(output or ""),
        "tokens_input": int(tokens_input or 0),
        "tokens_output": int(tokens_output or 0),
        "cost_usd": float(cost_usd or 0.0),
        "latency_ms": int(latency_ms or 0),
        "ai_credits_spent": float(ai_credits_spent or 0.0),
        "feedback": feedback
        if feedback is not None
        else {"score": None, "tags": []},
        "eval": {"auto_score": None, "notes": None},
        "metadata": metadata or {},
        "success": bool(success) if success is not None else _status_is_success((metadata or {}).get("status")),
        "task_type": task_type,
        "routing": routing or {},
        "hallucination_flags": hallucination_flags or (metadata or {}).get("hallucination_flags") or [],
        "user_rating": user_rating if user_rating is not None else (feedback or {}).get("score"),
    }

    preview = (output or "")[:80]
    if preview:
        entry["preview"] = preview

    append_ai_interaction(entry)
    try:
        create_ai_transfer_from_ledger_entry(entry)
    except Exception:
        logger.exception("Failed to create AI transfer entry", extra={"provider": provider, "model": model})
    return entry


def _filter_ai_interactions(
    interactions: list[dict],
    provider: str | None = None,
    model: str | None = None,
    wallet: str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> list[dict]:
    filtered = []
    for entry in interactions:
        if provider and str(entry.get("provider", "")) != provider:
            continue
        if model and str(entry.get("model", "")) != model:
            continue
        if wallet and str(entry.get("user_wallet", "")) != wallet:
            continue
        ts_raw = entry.get("timestamp")
        try:
            ts_val = int(ts_raw)
        except Exception:
            ts_val = None

        if from_ts is not None and ts_val is not None and ts_val < from_ts:
            continue
        if to_ts is not None and ts_val is not None and ts_val > to_ts:
            continue
        filtered.append(entry)
    return filtered


def _summarize_ai_metrics(interactions: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for entry in interactions:
        key = f"{entry.get('provider', 'unknown')}:{entry.get('model', 'unknown')}"
        bucket = summary.setdefault(
            key,
            {
                "calls": 0,
                "avg_latency_ms": 0.0,
                "avg_cost_usd": 0.0,
                "avg_feedback_score": None,
                "success_rate": 0.0,
            },
        )

        bucket["calls"] += 1
        bucket["avg_latency_ms"] += float(entry.get("latency_ms") or 0.0)
        bucket["avg_cost_usd"] += float(entry.get("cost_usd") or 0.0)
        bucket["success_rate"] += 1.0 if entry.get("success") else 0.0

        fb_score = None
        fb = entry.get("feedback") or {}
        try:
            fb_score = int(fb.get("score"))
        except Exception:
            fb_score = None

        if fb_score is not None:
            if bucket["avg_feedback_score"] is None:
                bucket["avg_feedback_score"] = 0.0
            bucket["avg_feedback_score"] += float(fb_score)

    for bucket in summary.values():
        calls = max(1, bucket["calls"])
        bucket["avg_latency_ms"] = bucket["avg_latency_ms"] / calls
        bucket["avg_cost_usd"] = bucket["avg_cost_usd"] / calls
        bucket["success_rate"] = bucket["success_rate"] / calls
        if bucket["avg_feedback_score"] is not None:
            bucket["avg_feedback_score"] = bucket["avg_feedback_score"] / calls

    return {"by_model": summary}


def _aggregate_model_metrics(interactions: list[dict]) -> dict:
    metrics: dict[str, dict] = {}

    for entry in interactions:
        key = f"{entry.get('provider', 'unknown')}:{entry.get('model', 'unknown')}"
        bucket = metrics.setdefault(
            key,
            {
                "calls": 0,
                "successes": 0,
                "latency_total": 0.0,
                "cost_total": 0.0,
                "hallucination_flags": Counter(),
                "rating_total": 0.0,
                "rating_count": 0,
            },
        )

        bucket["calls"] += 1
        bucket["latency_total"] += float(entry.get("latency_ms") or 0.0)
        bucket["cost_total"] += float(entry.get("cost_usd") or 0.0)
        if entry.get("success") is True or _status_is_success((entry.get("metadata") or {}).get("status")):
            bucket["successes"] += 1

        for flag in entry.get("hallucination_flags") or []:
            bucket["hallucination_flags"][str(flag)] += 1

        rating_val = entry.get("user_rating")
        if rating_val is None:
            fb = entry.get("feedback") or {}
            try:
                rating_val = float(fb.get("score")) if fb.get("score") is not None else None
            except Exception:
                rating_val = None
        if rating_val is not None:
            bucket["rating_total"] += float(rating_val)
            bucket["rating_count"] += 1

    result: dict[str, dict] = {}
    for key, bucket in metrics.items():
        calls = max(bucket.get("calls", 0), 1)
        hallucination_flags = bucket.get("hallucination_flags", Counter())
        result[key] = {
            "success_rate": bucket.get("successes", 0) / calls,
            "avg_cost": bucket.get("cost_total", 0.0) / calls,
            "avg_latency": bucket.get("latency_total", 0.0) / calls,
            "hallucination_flags": dict(hallucination_flags),
            "user_rating": (bucket.get("rating_total", 0.0) / bucket.get("rating_count", 1))
            if bucket.get("rating_count")
            else None,
            "calls": bucket.get("calls", 0),
        }

    return result


# ─── LIGHTWEIGHT CHAIN CACHE ────────────────────────────────────────────────
# Mining/miner support endpoints are latency-sensitive and should not block on
# repeated full-chain reads.  Keep a simple mtime-based cache for the chain and
# re-use derived views (e.g., reward-bearing blocks).
CHAIN_CACHE = {
    "mtime": 0.0,
    "chain": [],
    "reward_blocks": [],
}


def load_chain_cached():
    try:
        mtime = os.path.getmtime(CHAIN_FILE)
    except OSError:
        mtime = 0
    if CHAIN_CACHE["chain"] and CHAIN_CACHE["mtime"] == mtime:
        return CHAIN_CACHE["chain"]

    chain = load_json(CHAIN_FILE, [])
    reward_blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    CHAIN_CACHE.update({"mtime": mtime, "chain": chain, "reward_blocks": reward_blocks})
    return chain


def get_reward_blocks():
    if CHAIN_CACHE["reward_blocks"]:
        return CHAIN_CACHE["reward_blocks"]
    load_chain_cached()
    return CHAIN_CACHE["reward_blocks"]

def load_mempool():
    return load_json(MEMPOOL_FILE, [])

def save_mempool(pool):
    save_json(MEMPOOL_FILE, pool)

# ─── Token & Pool Helpers ────────────────────────────────────────────

def load_tokens():
    """Load the list of issued tokens from ``TOKENS_FILE``."""
    return load_json(TOKENS_FILE, [])

def save_tokens(tokens):
    """Persist the list of tokens to ``TOKENS_FILE``."""
    save_json(TOKENS_FILE, tokens)

def load_token_balances():
    """Load token balances per address per symbol."""
    return load_json(TOKEN_BALANCES_FILE, {})

def save_token_balances(balances):
    save_json(TOKEN_BALANCES_FILE, balances)

def load_pools():
    """Load all liquidity pools from ``POOLS_FILE``."""
    return load_json(POOLS_FILE, [])

def save_pools(pools):
    save_json(POOLS_FILE, pools)


def get_all_pools():
    return load_pools()


def _base_token_catalog():
    """Return metadata for the core Thronos tokens with supply details."""
    ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    l2e_ledger = load_json(L2E_LEDGER_FILE, {})

    def supply_of(ledger_map):
        try:
            return round(sum(float(v) for v in ledger_map.values()), 6)
        except Exception:
            return 0.0

    return [
        {
            "symbol": "THR",
            "name": "Thronos",
            "decimals": 6,
            "logo_url": url_for("static", filename="img/thronos-token.png", _external=False),
            "total_supply": supply_of(ledger),
            "type": "native",
        },
        {
            "symbol": "WBTC",
            "name": "Wrapped Bitcoin",
            "decimals": 8,
            "logo_url": url_for("static", filename="img/wbtc-logo.png", _external=False),
            "total_supply": supply_of(wbtc_ledger),
            "type": "wrapped",
        },
        {
            "symbol": "L2E",
            "name": "Learn-to-Earn",
            "decimals": 6,
            "logo_url": url_for("static", filename="img/l2e-logo.png", _external=False),
            "total_supply": supply_of(l2e_ledger),
            "type": "reward",
        },
    ]


def get_all_tokens():
    """Centralized catalog that returns base + custom tokens."""
    catalog = _base_token_catalog()

    custom_tokens = load_tokens()
    for t in custom_tokens:
        logo_path = t.get("logo_path") or t.get("logo")
        if logo_path:
            t["logo_url"] = url_for("media", filename=logo_path, _external=False)
        if t.get("symbol"):
            catalog.append(t)

    experimental = load_custom_tokens()
    for symbol, meta in experimental.items():
        token_id = meta.get("id")
        logo_path = meta.get("logo_path") or meta.get("logo")
        catalog.append({
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "decimals": meta.get("decimals", 6),
            "logo_url": url_for("media", filename=logo_path, _external=False) if logo_path else None,
            "total_supply": meta.get("total_supply") or meta.get("initial_supply"),
            "type": "experimental",
            "token_id": token_id,
        })

    return catalog


def get_wallet_balances(wallet: str):
    ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    l2e_ledger = load_json(L2E_LEDGER_FILE, {})

    thr_balance = round(float(ledger.get(wallet, 0.0)), 6)
    wbtc_balance = round(float(wbtc_ledger.get(wallet, 0.0)), 8)
    l2e_balance = round(float(l2e_ledger.get(wallet, 0.0)), 6)

    custom_token_balances = load_token_balances()
    prices_cache = {}

    def price_for(symbol):
        if symbol not in prices_cache:
            prices_cache[symbol] = get_token_price_in_thr(symbol)
        return prices_cache[symbol]

    tokens = [
        {
            "symbol": "THR",
            "name": "Thronos",
            "balance": thr_balance,
            "decimals": 6,
            "logo": "/static/img/thronos-token.png",
            "logo_url": url_for("static", filename="img/thronos-token.png"),
            "color": "#00ff66",
            "chain": "Thronos",
            "type": "native",
            "price_in_thr": 1.0,
            "value_in_thr": thr_balance,
        },
        {
            "symbol": "WBTC",
            "name": "Wrapped Bitcoin",
            "balance": wbtc_balance,
            "decimals": 8,
            "logo": "/static/img/wbtc-logo.png",
            "logo_url": url_for("static", filename="img/wbtc-logo.png"),
            "color": "#f7931a",
            "chain": "Thronos",
            "type": "wrapped",
            "price_in_thr": price_for("WBTC"),
            "value_in_thr": round(wbtc_balance * price_for("WBTC"), 6),
        },
        {
            "symbol": "L2E",
            "name": "Learn-to-Earn",
            "balance": l2e_balance,
            "decimals": 6,
            "logo": "/static/img/l2e-logo.png",
            "logo_url": url_for("static", filename="img/l2e-logo.png"),
            "color": "#00ccff",
            "chain": "Thronos",
            "type": "reward",
            "price_in_thr": price_for("L2E"),
            "value_in_thr": round(l2e_balance * price_for("L2E"), 6),
        },
    ]

    custom_tokens = load_custom_tokens()
    for symbol, token_data in custom_tokens.items():
        token_id = token_data.get("id")
        if not token_id:
            continue
        token_ledger = load_custom_token_ledger(token_id)
        token_balance = round(float(token_ledger.get(wallet, 0.0)), token_data.get("decimals", 6))

        # CRITICAL FIX #2: Use correct logo URL (media vs static)
        logo_path = resolve_token_logo(token_data)

        # If logo_path starts with "token_logos/", it's in MEDIA_DIR → use /media/
        # Otherwise (e.g., "img/..."), it's in static → use /static/
        if logo_path:
            if logo_path.startswith("token_logos/"):
                logo_url = f"/media/{logo_path}"
            else:
                logo_url = f"/static/{logo_path}"
        else:
            logo_url = None

        tokens.append({
            "symbol": symbol,
            "name": token_data.get("name", symbol),
            "balance": token_balance,
            "decimals": token_data.get("decimals", 6),
            "logo": logo_path,
            "logo_url": logo_url,
            "color": token_data.get("color", "#00ff66"),
            "chain": "Thronos",
            "type": "experimental",
            "token_id": token_id,
            "creator": token_data.get("creator", ""),
            "price_in_thr": price_for(symbol),
            "value_in_thr": round(token_balance * price_for(symbol), 6),
        })

    token_balances = {
        "THR": thr_balance,
        "WBTC": wbtc_balance,
        "L2E": l2e_balance,
    }
    for symbol, balances in custom_token_balances.items():
        try:
            token_balances[symbol] = round(float(balances.get(wallet, 0.0)), 6)
        except Exception:
            token_balances[symbol] = 0.0

    return {
        "thr": thr_balance,
        "wbtc": wbtc_balance,
        "l2e": l2e_balance,
        "token_balances": token_balances,
        "tokens": tokens,
    }

def load_attest_store():
    return load_json(ATTEST_STORE_FILE, {})

def save_attest_store(store):
    save_json(ATTEST_STORE_FILE, store)

# ─── Voting Helpers ─────────────────────────────────────────────────────

def load_voting():
    """Load voting data with default structure if file doesn't exist."""
    default = {
        "polls": [],
        "votes": {}
    }
    return load_json(VOTING_FILE, default)

def save_voting(voting_data):
    """Persist voting data to VOTING_FILE."""
    save_json(VOTING_FILE, voting_data)

def initialize_voting():
    """Initialize default voting polls for Crypto Hunters features."""
    voting_data = load_voting()

    # Only initialize if no polls exist
    if not voting_data.get("polls"):
        voting_data["polls"] = [
            {
                "id": "feature_pvp",
                "title": {
                    "en": "PvP Battle Arena",
                    "el": "Αρένα Μάχης PvP"
                },
                "description": {
                    "en": "Add player vs player combat zones",
                    "el": "Προσθήκη ζωνών μάχης παίκτη εναντίον παίκτη"
                },
                "votes": 0
            },
            {
                "id": "feature_guilds",
                "title": {
                    "en": "Guild System",
                    "el": "Σύστημα Συντεχνιών"
                },
                "description": {
                    "en": "Form teams and compete together",
                    "el": "Δημιουργήστε ομάδες και ανταγωνιστείτε μαζί"
                },
                "votes": 0
            },
            {
                "id": "feature_nft",
                "title": {
                    "en": "NFT Collectibles",
                    "el": "Συλλεκτικά NFT"
                },
                "description": {
                    "en": "Earn unique NFT rewards",
                    "el": "Κερδίστε μοναδικές ανταμοιβές NFT"
                },
                "votes": 0
            },
            {
                "id": "feature_staking",
                "title": {
                    "en": "THR Staking Rewards",
                    "el": "Ανταμοιβές Staking THR"
                },
                "description": {
                    "en": "Stake THR to earn passive rewards",
                    "el": "Κάντε stake THR για παθητικές ανταμοιβές"
                },
                "votes": 0
            },
            # New poll: allow the community to vote on deploying a second peer node for the
            # Crypto Hunters network.  A secondary peer improves redundancy and network
            # reliability.  This was requested so that users can participate in a more
            # decentralised manner.
            {
                "id": "feature_second_peer",
                "title": {
                    "en": "Second Peer Node",
                    "el": "Δεύτερος Κόμβος Peer"
                },
                "description": {
                    "en": "Deploy a second peer node to improve redundancy and reliability in the Crypto Hunters game network.",
                    "el": "Εγκατάσταση δεύτερου κόμβου peer για βελτίωση της αξιοπιστίας και ανθεκτικότητας του δικτύου του παιχνιδιού Crypto Hunters."
                },
                "votes": 0
            }
        ]
        voting_data["votes"] = {}
        save_voting(voting_data)

    return voting_data

def calculate_dynamic_fee(amount: float) -> float:
    """
    Calculates dynamic burn fee based on transaction amount.
    Higher amounts = Lower fee percentage (incentivizes larger transactions)

    Fee Tiers:
    - 0-10 THR:     0.5% (0.005)
    - 10-100 THR:   0.3% (0.003)
    - 100-1000 THR: 0.15% (0.0015)
    - 1000+ THR:    0.05% (0.0005)
    """
    if amount >= 1000:
        fee_rate = 0.0005  # 0.05%
    elif amount >= 100:
        fee_rate = 0.0015  # 0.15%
    elif amount >= 10:
        fee_rate = 0.003   # 0.3%
    else:
        fee_rate = 0.005   # 0.5%

    fee = amount * fee_rate
    return round(max(MIN_FEE, fee), 6)

# ─── Input Validation Helpers ───────────────────────────────────────────

def generate_thr_address(btc_address: str, timestamp: str = None) -> str:
    """
    Generate a deterministic THR address from BTC address.
    Format: THR + 40 hex characters
    """
    if timestamp is None:
        timestamp = str(int(time.time() * 1000))

    # Combine BTC address with timestamp for deterministic generation
    seed = f"{btc_address}:{timestamp}:thronos"
    # Double SHA256 for security
    hash1 = hashlib.sha256(seed.encode()).digest()
    hash2 = hashlib.sha256(hash1).hexdigest()

    # Take first 40 characters of the hex hash
    return f"THR{hash2[:40]}"

def validate_thr_address(address: str) -> bool:
    """
    Validate THR address format.
    Expected format: Starts with 'THR' followed by 40 hex characters.
    Example: THR1234567890abcdef1234567890abcdef12345678
    """
    if not address or not isinstance(address, str):
        return False

    # Remove whitespace
    address = address.strip()

    # Check format: THR + 40 hex chars
    if not address.startswith("THR"):
        return False

    hex_part = address[3:]
    if len(hex_part) != 40:
        return False

    # Check if hex_part contains only valid hex characters
    try:
        int(hex_part, 16)
        return True
    except ValueError:
        return False

def validate_amount(amount, min_amount=0.000001, max_amount=21000001) -> tuple[bool, str]:
    """
    Validate transaction amount.
    Returns: (is_valid, error_message)
    """
    try:
        amt = float(amount)
    except (ValueError, TypeError):
        return False, "Invalid amount format"

    if amt <= 0:
        return False, "Amount must be positive"

    if amt < min_amount:
        return False, f"Amount must be at least {min_amount} THR"

    if amt > max_amount:
        return False, f"Amount exceeds maximum ({max_amount} THR)"

    return True, ""

def validate_btc_address(address: str) -> bool:
    """
    Basic BTC address validation.
    Checks common formats: Legacy (1...), P2SH (3...), Bech32 (bc1...)
    """
    if not address or not isinstance(address, str):
        return False

    address = address.strip()

    # Legacy P2PKH (starts with 1)
    if address.startswith("1") and 26 <= len(address) <= 35:
        return True

    # P2SH (starts with 3)
    if address.startswith("3") and 26 <= len(address) <= 35:
        return True

    # Bech32 (starts with bc1)
    if address.startswith("bc1") and 42 <= len(address) <= 62:
        return True

    return False

# -------------------------------------------------------------------------
# Course registry helpers for Learn‑to‑Earn
#
# Courses are persisted in a simple JSON file under ``COURSES_FILE``.
# Each course is represented as a dictionary with the following keys:
#   id: unique identifier (UUID string)
#   title: human‑readable name
#   teacher: THR address of the instructor
#   price_thr: cost in THR tokens to enroll (float)
#   reward_l2e: L2E token reward for completion (float)
#   students: list of THR addresses currently enrolled
#   completed: list of THR addresses who have completed the course
#
# These helpers load and save the course list.

def load_courses():
    return load_json(COURSES_FILE, [])

def save_courses(courses):
    save_json(COURSES_FILE, courses)


def load_enrollments():
    return load_json(L2E_ENROLLMENTS_FILE, {})


def save_enrollments(enrollments):
    save_json(L2E_ENROLLMENTS_FILE, enrollments)

# -------------------------------------------------------------------------
# Peer registry and broadcast helpers
#
# Thronos v3.7 introduces a rudimentary peer‑to‑peer network.  Each node
# maintains a list of known peers in ``peers.json``.  These helpers load and
# persist the peer list and provide simple broadcast functions for
# transactions and blocks.  Networking here is best‑effort: failed HTTP
# requests are silently ignored.  In future versions, failure handling and
# peer pruning could be added.

def load_peers() -> list:
    """Load the list of known peer URLs from ``PEERS_FILE``.  Returns an
    empty list if the file does not exist or is invalid."""
    return load_json(PEERS_FILE, [])


def save_peers(peers: list) -> None:
    """Persist the peer list to ``PEERS_FILE``."""
    # ensure unique entries while preserving order
    seen = set()
    unique = []
    for p in peers:
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    save_json(PEERS_FILE, unique)


def broadcast_tx(tx: dict) -> None:
    """Broadcast a single transaction to all known peers.  Uses a POST
    request to the peer's ``/api/v1/receive_tx`` endpoint.  Errors during
    broadcast are ignored."""
    peers = load_peers()
    for peer in peers:
        try:
            # ensure trailing slash is not duplicated
            url = peer.rstrip("/") + "/api/v1/receive_tx"
            requests.post(url, json=tx, timeout=3)
        except Exception:
            pass


def broadcast_block(block: dict) -> None:
    """Broadcast a mined block to all known peers.  Uses a POST
    request to the peer's ``/api/v1/receive_block`` endpoint.  Errors during
    broadcast are ignored."""
    peers = load_peers()
    for peer in peers:
        try:
            url = peer.rstrip("/") + "/api/v1/receive_block"
            requests.post(url, json=block, timeout=3)
        except Exception:
            pass

# --- AI Packs & Credits helpers ------------------------------------------------

AI_DEFAULT_PACKS = [
    {
        "code": "Q-100",
        "title": "Quantum Explorer 100",
        "description": "Για light χρήση, tests και μικρά prompts.",
        "credits": 100,
        "price_thr": 5.0,
    },
    {
        "code": "Q-500",
        "title": "Researcher 500",
        "description": "Σταθερή καθημερινή χρήση του Quantum Chat.",
        "credits": 500,
        "price_thr": 20.0,
    },
    {
        "code": "Q-2000",
        "title": "Validator 2000",
        "description": "Για power-users, devs και validators του Thronos.",
        "credits": 2000,
        "price_thr": 60.0,
    },
]

# Πόσα credits καίει κάθε AI μήνυμα
AI_CREDIT_COST_PER_MSG = int(os.getenv("AI_CREDIT_COST_PER_MSG", "1"))

def load_ai_packs():
    """Διαβάζει τα διαθέσιμα packs από αρχείο, αλλιώς επιστρέφει τα default."""
    data = load_json(AI_PACKS_FILE, None)
    if isinstance(data, list) and data:
        return data
    return AI_DEFAULT_PACKS


def save_ai_packs(packs):
    """Αν θες κάποια στιγμή να αλλάζεις δυναμικά τα packs."""
    save_json(AI_PACKS_FILE, packs)


def load_ai_credits():
    """wallet -> σύνολο credits"""
    return load_json(AI_CREDITS_FILE, {})


def save_ai_credits(credits):
    save_json(AI_CREDITS_FILE, credits)

# ---------------------------------------------------------------------------
# Free usage counters
# ---------------------------------------------------------------------------
def load_ai_free_usage():
    """
    Load the free usage counters from disk.  The returned value is a
    dictionary mapping session identifiers to the number of demo messages
    already consumed.  If the file does not exist, an empty dictionary is
    returned.
    """
    return load_json(AI_FREE_USAGE_FILE, {})


def save_ai_free_usage(counters):
    """
    Persist the free usage counters back to disk.  Accepts a dict mapping
    session_id strings to integers.  The file is stored in JSON format.
    """
    save_json(AI_FREE_USAGE_FILE, counters)

def load_ai_sessions():

    """Load AI sessions list (robust to legacy formats)."""
    def _now():
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    data = load_json(AI_SESSIONS_FILE, default=[])
    if isinstance(data, dict):
        if isinstance(data.get("sessions"), list):
            data = data["sessions"]
        else:
            merged = []
            for w, lst in data.items():
                if isinstance(lst, list):
                    for s in lst:
                        if isinstance(s, dict) and "wallet" not in s:
                            s = {**s, "wallet": w}
                        merged.append(s)
            data = merged

    if not isinstance(data, list):
        data = []

    out = []
    for s in data:
        if not isinstance(s, dict):
            continue
        sid = s.get("id") or s.get("session_id") or str(uuid.uuid4())
        wallet = (s.get("wallet") or s.get("thr_wallet") or "").strip()
        created = s.get("created_at") or s.get("created") or _now()
        updated = s.get("updated_at") or s.get("updated") or created
        out.append({
            "id": sid,
            "wallet": wallet,
            "title": s.get("title") or s.get("name") or "New Chat",
            "created_at": created,
            "updated_at": updated,
            "archived": bool(s.get("archived", False)),
            "model": s.get("model") or s.get("ai_model") or None,
            "message_count": int(s.get("message_count") or s.get("messages_count") or 0),
            "meta": s.get("meta") if isinstance(s.get("meta"), dict) else {},
        })
    return out

def save_ai_sessions(sessions):

    # persist as a plain list for simplicity
    if not isinstance(sessions, list):
        sessions = []
    save_json(AI_SESSIONS_FILE, sessions)


def _session_messages_path(session_id: str) -> str:
    safe_id = str(session_id or "").replace("/", "_")
    return os.path.join(AI_SESSIONS_DIR, f"{safe_id}.json")


def ensure_session_messages_file(session_id: str):
    if not session_id:
        return
    path = _session_messages_path(session_id)
    os.makedirs(AI_SESSIONS_DIR, exist_ok=True)
    if not os.path.exists(path):
        save_json(path, [])


def load_session_messages(session_id: str) -> list:
    """
    Load messages for a session, sorted by timestamp.
    FIX 3: Migrates old messages without msg_id/timestamp.
    """
    if not session_id:
        return []
    path = _session_messages_path(session_id)
    messages = load_json(path, []) or []

    # FIX 3: Migration for old sessions without msg_id/ts
    needs_save = False
    for i, msg in enumerate(messages):
        # Add msg_id if missing
        if "msg_id" not in msg:
            msg["msg_id"] = f"msg_migrated_{i}_{secrets.token_hex(4)}"
            needs_save = True

        # Add timestamp if missing (use epoch for old messages)
        if "timestamp" not in msg or not msg["timestamp"]:
            msg["timestamp"] = "1970-01-01T00:00:00Z"
            needs_save = True

        # Ensure ts shorthand exists for compatibility
        if "ts" not in msg and "timestamp" in msg:
            msg["ts"] = msg["timestamp"]
            needs_save = True

    # Save if we migrated any messages
    if needs_save:
        save_session_messages(session_id, messages)

    messages.sort(key=lambda m: m.get("timestamp", ""))
    return messages


def session_messages_exists(session_id: str) -> bool:
    """Check if a transcript file exists for the given session id."""
    if not session_id:
        return False
    path = _session_messages_path(session_id)
    return os.path.exists(path)


def save_session_messages(session_id: str, messages: list):
    """Save messages for a session."""
    if not session_id:
        return
    ensure_session_messages_file(session_id)
    path = _session_messages_path(session_id)
    save_json(path, messages)


def remove_session_from_index(session_id: str, wallet: str | None = None):
    """Remove a session from the index, optionally scoped by wallet."""
    if not session_id:
        return
    sessions = load_ai_sessions()
    new_sessions = []
    for s in sessions:
        if s.get("id") != session_id:
            new_sessions.append(s)
            continue
        if wallet and s.get("wallet") != wallet:
            new_sessions.append(s)
    if len(new_sessions) != len(sessions):
        save_ai_sessions(new_sessions)


def append_session_transcript(session_id: str, prompt: str, response: str, files, timestamp: str):
    """Persist a conversation turn to the per-session transcript file."""
    if not session_id:
        return

    path = _session_messages_path(session_id)
    os.makedirs(AI_SESSIONS_DIR, exist_ok=True)
    transcript = load_json(path, [])

    if prompt:
        transcript.append({
            "role": "user",
            "content": prompt,
            "timestamp": timestamp,
            "session_id": session_id,
        })

    if response:
        entry = {
            "role": "assistant",
            "content": response,
            "timestamp": timestamp,
            "session_id": session_id,
        }
        if files:
            entry["files"] = files
        transcript.append(entry)

    transcript = transcript[-400:]
    save_json(path, transcript)


def ensure_session_exists(session_id: str, wallet: str | None) -> dict:
    """
    FIX 9: Return an existing session or recreate it on disk.
    Graceful degradation - returns empty dict on errors.
    """
    if not session_id:
        return {}

    try:
        sessions = load_ai_sessions()
        for s in sessions:
            if s.get("id") == session_id:
                ensure_session_messages_file(session_id)
                return s

        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        recovered = {
            "id": session_id,
            "wallet": (wallet or "").strip(),
            "title": "Recovered Session",
            "created_at": now,
            "updated_at": now,
            "archived": False,
            "model": None,
            "message_count": 0,
            "meta": {"recovered": True},
        }
        sessions.append(recovered)
        save_ai_sessions(sessions)
        ensure_session_messages_file(session_id)
        logger.info(f"Session recovered: {session_id} (wallet: {wallet})")
        return recovered
    except Exception as e:
        logger.error(f"Failed to ensure session {session_id}: {e}")
        return {}  # Graceful degradation


def generate_stable_session_key(wallet: str | None = None) -> str:
    """
    FIX 9: Generate stable session key.

    - If wallet provided: deterministic key based on wallet + timestamp (day)
    - If no wallet (guest): random UUID

    This ensures sessions are stable across requests for same wallet on same day.
    """
    if wallet:
        # Deterministic key: wallet + date (changes daily for privacy)
        from datetime import date
        today = date.today().isoformat()
        seed = f"{wallet}:{today}"
        # Use first 16 chars of sha256 hash
        import hashlib
        hash_hex = hashlib.sha256(seed.encode()).hexdigest()[:16]
        return f"session_{hash_hex}"
    else:
        # Guest mode: random UUID
        return str(uuid.uuid4())


def register_session(session_data: dict) -> bool:
    """
    FIX 9: Register/update a session in the canonical store.
    Wrapper around ensure_session_exists with graceful degradation.

    Args:
        session_data: {"session_id": str, "user_wallet": str | None, ...}

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        session_id = session_data.get("session_id")
        if not session_id:
            return False

        wallet = session_data.get("user_wallet") or session_data.get("wallet")
        ensure_session_exists(session_id, wallet)
        return True
    except Exception as e:
        logger.error(f"Failed to register session: {e}")
        return False  # Graceful degradation


def attach_uploaded_files_to_session(session_id: str, wallet: str, files: list):
    """
    Link uploaded file metadata to a session, so the agent can see them.
    This only stores references (ids + names), not content.
    """
    sessions = load_ai_sessions()
    for s in sessions:
        if s.get("id") == session_id and (not wallet or s.get("wallet") == wallet):
            s.setdefault("uploaded_files", [])
            # de-dup by id
            existing = {f.get("id") for f in s.get("uploaded_files", []) if isinstance(f, dict)}
            for fmeta in files:
                if fmeta.get("id") not in existing:
                    s["uploaded_files"].append(fmeta)
            save_ai_sessions(sessions)
            return

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def target_to_bits(target: int) -> int:
    if target == 0:
        return 0
    target_hex = hex(target)[2:]
    if len(target_hex) % 2 != 0:
        target_hex = "0" + target_hex
    target_bytes = bytes.fromhex(target_hex)
    if target_bytes[0] >= 0x80:
        target_bytes = b"\\x00" + target_bytes
    exponent = len(target_bytes)
    coefficient = target_bytes[:3]
    if len(coefficient) < 3:
        coefficient = coefficient + b"\\x00" * (3 - len(coefficient))
    return (exponent << 24) | int.from_bytes(coefficient, "big")

def calculate_reward(height: int) -> float:
    halvings = height // 210000
    if halvings > 9:
        return 0.0
    return round(1.0 / (2 ** halvings), 6)

def recompute_height_offset_from_ledger():
    """
    Διαβάζει ledger + chain και βρίσκει πόσα THR έχουν εκδοθεί
    ΠΡΙΝ αρχίσουν να γράφονται blocks στο phantom_tx_chain.json.

    Το μεταφράζει σε ισοδύναμο αριθμό blocks σύμφωνα με
    το halving schedule (1.0, 0.5, 0.25, …).
    """
    global HEIGHT_OFFSET

    ledger = load_json(LEDGER_FILE, {})
    chain  = load_json(CHAIN_FILE, [])

    # Όσα blocks υπάρχουν ΗΔΗ στο chain
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    minted_from_blocks = sum(float(b.get("reward", 0.0)) for b in blocks)

    # Συνολικό supply από ledger (άθροισμα όλων των διευθύνσεων)
    total_ledger = sum(float(v) for v in ledger.values())

    # Ό,τι περισσεύει το θεωρούμε "παλιό supply χωρίς blocks"
    pre_mined = max(0.0, total_ledger - minted_from_blocks)

    if pre_mined <= 0:
        HEIGHT_OFFSET = 0
        logger.info("No pre-mined supply detected. HEIGHT_OFFSET = 0")
        return

    remaining = pre_mined
    h = 0
    # Μέχρι max ~2.1M blocks, δεν μας νοιάζει απόδοση, είναι startup-only
    while remaining > 0 and h < 2_100_000:
        r = calculate_reward(h)
        if r <= 0:
            break
        remaining -= r
        h += 1

    HEIGHT_OFFSET = h
    logger.info(
        f"[SUPPLY] Pre-mined ≈ {pre_mined:.6f} THR -> HEIGHT_OFFSET = {HEIGHT_OFFSET}"
    )


def update_last_block(entry, is_block=True):
    """
    Γράφει last_block.json αλλά πλέον κρατά και:
    - block_count (με offset)
    - total_supply (άθροισμα ledger)
    ώστε η αρχική σελίδα να ξέρει ΠΟΣΑ block και ΠΟΣΟ supply έχουμε.
    """
    chain  = load_json(CHAIN_FILE, [])
    ledger = load_json(LEDGER_FILE, {})

    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    block_count = HEIGHT_OFFSET + len(blocks)

    total_supply = round(sum(float(v) for v in ledger.values()), 6)

    # Build the summary for the last block or transaction.  When
    # ``is_block`` is False (e.g. for a transaction update), we want to
    # preserve the existing block height and hash in last_block.json.  This
    # prevents the viewer/home page from incorrectly showing the last
    # transaction as the latest block.  Only ``block_count`` and
    # ``total_supply`` should be updated in that case.
    summary = {
        "height":     entry.get("height"),
        "block_hash": entry.get("block_hash") or entry.get("tx_id"),
        "timestamp":  entry.get("timestamp"),
        "thr_address": entry.get("thr_address"),
        "type": "block" if is_block else entry.get("type", "transfer"),
        "block_count": block_count,
        "total_supply": total_supply,
    }
    if not is_block:
        # Preserve the latest block information when updating due to
        # transactions or other non-block events.
        existing = load_json(LAST_BLOCK_FILE, {})
        if existing:
            summary["height"] = existing.get("height")
            summary["block_hash"] = existing.get("block_hash")
            summary["timestamp"] = existing.get("timestamp")
            summary["thr_address"] = existing.get("thr_address")
    save_json(LAST_BLOCK_FILE, summary)

def verify_btc_payment(btc_address, min_amount=MIN_AMOUNT):
    try:
        txns = get_btc_txns(btc_address, BTC_RECEIVER)
        paid = any(tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= min_amount for tx in txns)
        return paid, txns
    except Exception as e:
        logger.error(f"Watcher Error: {e}")
        return False, []

def get_mining_target():
    blocks = get_reward_blocks()
    if len(blocks) < RETARGET_INTERVAL:
        return INITIAL_TARGET
    last_block  = blocks[-1]
    last_target = int(last_block.get("target", INITIAL_TARGET))
    if len(blocks) % RETARGET_INTERVAL != 0:
        return last_target
    start_block = blocks[-RETARGET_INTERVAL]
    try:
        t_fmt = "%Y-%m-%d %H:%M:%S UTC"
        t_end = datetime.strptime(last_block["timestamp"], t_fmt).timestamp()
        t_sta = datetime.strptime(start_block["timestamp"], t_fmt).timestamp()
    except Exception as e:
        logger.error(f"Time parse error: {e}")
        return last_target
    actual = max(1, t_end - t_sta)
    expected = RETARGET_INTERVAL * TARGET_BLOCK_TIME
    ratio = actual / expected
    ratio = 0.25 if ratio < 0.25 else (4.0 if ratio > 4.0 else ratio)
    new_target = int(last_target * ratio)
    if new_target > INITIAL_TARGET:
        new_target = INITIAL_TARGET
    return new_target


# ─── AI FILE / CORPUS HELPERS ──────────────────────
def extract_ai_files_from_text(full_text: str):
    """
    Ψάχνει για blocks τύπου:
      [[FILE:filename.ext]]
      ...περιεχόμενο...
      [[/FILE]]
    Γράφει τα αρχεία στο AI_FILES_DIR και επιστρέφει:
      files: list[ {filename, path, size} ]
      cleaned_text: text χωρίς τα raw blocks.
    """
    files = []
    cleaned_parts = []
    i = 0
    while True:
        start = full_text.find("[[FILE:", i)
        if start == -1:
            cleaned_parts.append(full_text[i:])
            break

        # ό,τι υπάρχει πριν το block
        cleaned_parts.append(full_text[i:start])

        end_name = full_text.find("]]", start)
        if end_name == -1:
            # δεν κλείνει σωστά, κρατάμε όλο το υπόλοιπο
            cleaned_parts.append(full_text[start:])
            break

        filename = full_text[start + len("[[FILE:"):end_name].strip()
        end_block = full_text.find("[[/FILE]]", end_name)
        if end_block == -1:
            cleaned_parts.append(full_text[start:])
            break

        content = full_text[end_name + 2:end_block]

        # ασφαλές όνομα αρχείου
        safe_name = filename.replace("..", "_").replace("/", "_").replace("\\", "_")
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            size = len(content.encode("utf-8"))
            files.append({
                "filename": safe_name,
                "path": file_path,
                "size": size,
            })
            cleaned_parts.append(f"\\n[AI file generated: {safe_name}]\\n")
        except Exception as e:
            print("AI file write error:", e)
            cleaned_parts.append(f"\\n[AI file error: {safe_name}]\\n")

        i = end_block + len("[[/FILE]]")

    cleaned_text = "".join(cleaned_parts).strip()
    return files, cleaned_text


@app.route("/api/ai/generated/<filename>", methods=["GET"])
def api_ai_generated_file(filename):
    """
    Download ενός AI-generated αρχείου από το AI_FILES_DIR.
    Χρησιμοποιείται από /chat και /architect για τα [[FILE:...]].
    """
    safe_name = filename.replace("..", "_").replace("/", "_").replace("\\", "_")
    path = os.path.join(AI_FILES_DIR, safe_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "file not found"}), 404

    mime, _ = mimetypes.guess_type(safe_name)
    return send_file(
        path,
        as_attachment=True,
        download_name=safe_name,
        mimetype=mime or "application/octet-stream",
    )


def enqueue_offline_corpus(wallet: str, prompt: str, response: str, files, session_id: str | None = None):
    """
    Ελαφρύ offline corpus για Whisper / training + sessions.
    Κρατάμε και session_id ώστε να χωρίζονται οι συνομιλίες τύπου ChatGPT.
    """
    sid = session_id or "default"

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    entry = {
        "timestamp": ts,
        "wallet": wallet or "",
        "prompt": prompt,
        "response": response,
        "files": [f.get("filename") for f in files] if files else [],
        "session_id": sid,
    }

    corpus = load_json(AI_CORPUS_FILE, [])
    corpus.append(entry)
    corpus = corpus[-1000:]
    save_json(AI_CORPUS_FILE, corpus)
    append_session_transcript(sid, prompt, response, files, ts)

    # update / create session meta
    if wallet:
        sessions = load_ai_sessions()
        found = None
        for s in sessions:
            if s.get("wallet") == wallet and s.get("id") == sid:
                found = s
                break

        if not found:
            title_src = prompt.strip() or "Νέα συνομιλία"
            title = (title_src.replace("\\n", " ")[:80]).strip()
            found = {
                "id": sid,
                "wallet": wallet,
                "title": title or "Νέα συνομιλία",
                "created_at": ts,
                "updated_at": ts,
            }
            sessions.append(found)
        else:
            found["updated_at"] = ts

        save_ai_sessions(sessions)


# ─── VIEWER HELPERS ────────────────────────────────
def get_blocks_for_viewer():
    chain = load_json(CHAIN_FILE, [])
    raw_blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    blocks = []
    for b in raw_blocks:
        height = b.get("height")
        if height is None:
            height = len(blocks)
        block_txs = [
            tx for tx in chain
            if tx.get("type") in ("transfer", "coinbase", "service_payment", "ai_knowledge", "token_transfer", "token_create", "token_mint", "token_burn", "swap", "bridge")
            and tx.get("height") == height
        ]
        rsplit = b.get("reward_split") or {}
        reward_to_miner = float(rsplit.get("miner", b.get("reward_to_miner", 0.0)))
        reward_to_ai    = float(rsplit.get("ai", 0.0))
        burn_from_split = float(rsplit.get("burn", 0.0))
        # Include swap fees (stored as "fee") and regular fees (stored as "fee_burned")
        fees_from_txs   = sum(float(tx.get("fee_burned", 0.0) or tx.get("fee", 0.0)) for tx in block_txs)
        blocks.append({
            "index": height,
            "hash": b.get("block_hash",""),
            "fee_burned": round(burn_from_split + fees_from_txs, 6),
            "reward_to_miner": reward_to_miner,
            "reward_to_ai": reward_to_ai,
            "is_stratum": bool(b.get("is_stratum")),
            "nonce": b.get("nonce","-"),
            "transactions": block_txs,
            "timestamp": b.get("timestamp","")
        })
    blocks.sort(key=lambda x: x["index"], reverse=True)
    return blocks

def get_transactions_for_viewer():
    chain = load_json(CHAIN_FILE, [])
    pool  = load_mempool()

    # Confirmed txs από το chain (including swaps)
    chain_txs = [
        t for t in chain
        if isinstance(t, dict)
        and t.get("type") in ["transfer", "service_payment", "ai_knowledge", "coinbase", "swap", "bridge"]
    ]

    # Pending από mempool (χωρίς height)
    pending_txs = [
        t for t in pool
        if isinstance(t, dict)
        and t.get("type") in ["transfer", "service_payment", "ai_knowledge", "swap", "bridge"]
    ]

    all_txs = chain_txs + pending_txs

    out = []
    for t in all_txs:
        preview = ""
        details_payload = t.get("details")
        details = details_payload if isinstance(details_payload, dict) else None
        tx_type = t.get("type", "transfer")

        if tx_type == "ai_knowledge":
            payload = t.get("ai_payload") or ""
            payload_obj: dict[str, Any] = {}
            if isinstance(payload, str):
                try:
                    payload_obj = json.loads(payload)
                except Exception:
                    payload_obj = {}

            preview = "Legacy AI TX (prompt_tail truncated)"
            if details is None:
                details = {
                    "kind": "ai_knowledge_legacy",
                    "provider": payload_obj.get("provider"),
                    "model": payload_obj.get("model"),
                    "has_prompt_tail": bool(payload_obj.get("prompt_tail")),
                    "has_response_tail": bool(payload_obj.get("response_tail")),
                }

        if details and details.get("kind") == "ai_interaction" and not preview:
            preview = "AI interaction transfer"

        tx_from = t.get("from", "Unknown")
        tx_to   = t.get("to",   "Unknown")
        height  = t.get("height")  # μπορεί να είναι None για pending
        fee     = t.get("fee_burned", 0.0)
        amount  = t.get("amount", 0.0)
        token_symbol = t.get("token_symbol", "THR")

        # Handle swap transactions specially
        if tx_type == "swap":
            fee = t.get("fee", 0.0)
            amount = t.get("amount_in", 0.0)
            token_in = t.get("token_in", "THR")
            token_out = t.get("token_out", "wBTC")
            amount_out = t.get("amount_out", 0.0)
            preview = f"SWAP {amount:.6f} {token_in} → {amount_out:.8f} {token_out}"
            token_symbol = token_in

        # Handle bridge transactions
        if tx_type == "bridge":
            preview = f"BRIDGE {t.get('direction', 'THR→BTC')}"
            token_symbol = t.get("token", "THR")

        tx_id = t.get("tx_id")
        if not tx_id and tx_type == "coinbase":
            tx_id = f"COINBASE-{height}"

        out.append({
            "tx_id":     tx_id or "N/A",
            "height":    height,
            "from":      tx_from,
            "to":        tx_to,
            "amount":    amount,
            "fee_burned": fee,
            "timestamp": t.get("timestamp", ""),
            "type":      tx_type,
            "note":      preview,
            "details":   details,
            "token_symbol": token_symbol,
        })

    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def ensure_ai_wallet():
    pledges = load_json(PLEDGE_CHAIN, [])
    ai_pledge = next((p for p in pledges if p.get("thr_address")==AI_WALLET_ADDRESS), None)
    if ai_pledge: 
        print(f"🤖 AI Wallet {AI_WALLET_ADDRESS} ready.")
        return
    print(f"🤖 Initializing AI Agent Wallet: {AI_WALLET_ADDRESS}")
    send_seed      = secrets.token_hex(16)
    send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
    send_auth_hash = hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()
    new_pledge = {
        "btc_address":"SYSTEM_AI_RESERVE",
        "pledge_text":"Thronos AI Agent Genesis Allocation",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash":"AI_GENESIS_"+secrets.token_hex(8),
        "thr_address":AI_WALLET_ADDRESS,
        "send_seed_hash":send_seed_hash,
        "send_auth_hash":send_auth_hash,
        "has_passphrase":False,
        "is_system":True
    }
    pledges.append(new_pledge)
    save_json(PLEDGE_CHAIN, pledges)
    creds = {
        "thr_address":AI_WALLET_ADDRESS,
        "auth_secret":send_seed,
        "note":"Put these in ai_agent/agent_config.json"
    }
    save_json(AI_CREDS_FILE, creds)
    print(f"✅ AI Wallet Registered. Credentials saved to {AI_CREDS_FILE}")


def decode_iot_steganography(image_path):
    try:
        img = Image.open(image_path)
        width, height = img.size
        pixels = img.load()
        delimiter = "###END###"
        chars=[]
        cur=""
        for y in range(height):
            for x in range(width):
                r,g,b = pixels[x,y]
                for val in (r,g,b):
                    cur += str(val & 1)
                    if len(cur)==8:
                        chars.append(chr(int(cur,2)))
                        cur=""
                        if len(chars)>=len(delimiter) and "".join(chars[-len(delimiter):])==delimiter:
                            json_str = "".join(chars[:-len(delimiter)])
                            return json.loads(json_str)
        return None
    except Exception as e:
        print("Stego Decode Error:", e)
        return None


# ─── WRITE PROTECTION FOR REPLICA NODES ───────────────────────────────────
@app.before_request
def block_writes_on_replica():
    """
    Replica nodes are read-only. Block all write operations (POST, PUT, DELETE)
    except for heartbeat endpoint.
    """
    if NODE_ROLE == "replica":
        # Allow heartbeat from replica to master
        if request.path == "/api/peers/heartbeat":
            return None
        # Block all write operations
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            return jsonify({
                "error": "Write operations not allowed on replica node",
                "node_role": "replica",
                "hint": "Direct writes to master node"
            }), 403
    return None


# ─── BASIC PAGES ───────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html", game_panel_url=GAME_PANEL_URL)

@app.route("/contracts/<path:filename>")
def serve_contract(filename):
    return send_from_directory(CONTRACTS_DIR, filename)

@app.route("/media/<path:filename>")
def media(filename):
    """Serve persistent media assets from the data volume."""
    safe_name = filename.lstrip("/..")
    return send_from_directory(MEDIA_DIR, safe_name)

@app.route("/viewer")
def viewer():
    return render_template(
        "thronos_block_viewer.html",
        blocks=get_blocks_for_viewer(),
        transactions=get_transactions_for_viewer(),
    )

@app.route("/wallet")
def wallet_page():
    thr_addr = request.args.get("address")
    return render_template("wallet_viewer.html", thr_address=thr_addr)


@app.route("/api/wallet/qr/<thr_addr>")
def wallet_qr_code(thr_addr):
    """Generate QR code image for the given THR address."""
    img = qrcode.make(thr_addr)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/wallet/audio/<thr_addr>")
def wallet_audio(thr_addr):
    """Generate WAV audio encoding the THR address."""
    binary_data = ''.join(format(ord(c), '08b') for c in thr_addr) + '00000000'
    framerate = 44100
    tone_duration = 0.1
    pause_duration = 0.05
    t_bit = np.linspace(0, tone_duration, int(framerate * tone_duration), endpoint=False)
    waveform = np.array([], dtype=np.int16)
    for bit in binary_data:
        freq = 880 if bit == '1' else 440
        tone = (32767 * np.sin(2 * np.pi * freq * t_bit)).astype(np.int16)
        silence = np.zeros(int(framerate * pause_duration), dtype=np.int16)
        waveform = np.concatenate((waveform, tone, silence))
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(waveform.tobytes())
    buf.seek(0)
    return send_file(buf, mimetype="audio/wav", download_name="ThronosAddress.wav")

@app.route("/send")
def send_page():
    return render_template("send.html")

@app.route("/tokenomics")
def tokenomics_page():
    return render_template("tokenomics.html")

@app.route("/whitepaper")
def whitepaper_page():
    return render_template("whitepaper.html")

@app.route("/roadmap")
def roadmap_page():
    return render_template("roadmap.html")

@app.route("/token_chart")
def token_chart_page():
    return render_template("token_chart.html")

# NEW service pages
@app.route("/bridge")
def bridge_page():
    return render_template("bridge.html")

@app.route("/iot")
def iot_page():
    return render_template("iot.html")

@app.route("/swap")
def swap_page():
    return render_template("swap.html")

@app.route("/gateway")
def gateway_page():
    return render_template("gateway.html", stripe_key=STRIPE_PUBLISHABLE_KEY)

# Learn‑to‑Earn courses page
@app.route("/courses")
def courses_page():
    """
    Render the Learn‑to‑Earn courses interface.  This page allows users to
    browse available courses, enroll by paying in THR, complete courses
    (rewarding L2E tokens), and create new courses if they are
    authenticated teachers.  The client‑side logic uses the
    ``/api/v1/courses`` endpoints for data operations.
    """
    return render_template("courses.html")


@app.route("/courses/<string:course_id>")
def course_detail_page(course_id: str):
    """Render a single course page with media and quiz access."""
    return render_template("course_detail.html", course_id=course_id)

# ---------------------------------------------------------------------------

# Train-to-Earn page route (to be inserted after courses route in server.py)

@app.route("/train2earn")
def train2earn_page():
    """
    Render the Train-to-Earn interface. This page allows users to
    contribute training data for AI models, earn T2E tokens for their
    contributions, and view their contribution history.
    """
    return render_template("train2earn.html")

# Train-to-Earn API endpoints
@app.route("/api/v1/train2earn/contribute", methods=["POST"])
def api_train2earn_contribute():
    """
    Accept training data contributions from users.
    Rewards contributors with T2E tokens based on contribution type.
    """
    data = request.get_json() or {}
    contributor = (data.get("contributor") or "").strip()
    contrib_type = (data.get("type") or "").strip()
    content = data.get("content", {})
    tags = data.get("tags", [])
    reward = float(data.get("reward_t2e", 5.0))
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    
    if not contributor or not contrib_type or not content:
        return jsonify(status="error", message="Missing required fields"), 400
    
    # Verify contributor authentication
    pledges = load_json(PLEDGE_CHAIN, [])
    contributor_pledge = next((p for p in pledges if p.get("thr_address") == contributor), None)
    if not contributor_pledge:
        return jsonify(status="error", message="Contributor not found"), 404
    
    stored_auth_hash = contributor_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Auth not enabled"), 400
    
    if contributor_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403
    
    # Store contribution (simplified - in production, validate and process content)
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    contribution_id = f"T2E-{int(time.time())}-{secrets.token_hex(4)}"
    
    # Award T2E tokens (placeholder ledger - you may want a separate T2E ledger)
    # For now, we'll use a simple file-based approach
    t2e_file = os.path.join(DATA_DIR, "t2e_contributions.json")
    contributions = load_json(t2e_file, [])
    
    contribution = {
        "id": contribution_id,
        "contributor": contributor,
        "type": contrib_type,
        "content_hash": hashlib.sha256(json.dumps(content).encode()).hexdigest(),
        "tags": tags,
        "reward_t2e": reward,
        "timestamp": ts,
        "status": "accepted"
    }
    
    contributions.append(contribution)
    save_json(t2e_file, contributions)
    
    # Log to AI corpus for training
    try:
        if contrib_type in ["conversation", "qa"]:
            user_msg = content.get("user", "")
            assistant_msg = content.get("assistant", "")
            enqueue_offline_corpus(contributor, user_msg, assistant_msg, [], session_id=None)
    except Exception as e:
        print(f"T2E corpus logging error: {e}")
    
    return jsonify(status="success", tx_id=contribution_id, reward=reward), 200

@app.route("/api/v1/train2earn/contributions/<thr_addr>", methods=["GET"])
def api_train2earn_contributions(thr_addr: str):
    """
    Return contribution history for a specific contributor.
    """
    t2e_file = os.path.join(DATA_DIR, "t2e_contributions.json")
    contributions = load_json(t2e_file, [])
    
    user_contributions = [
        c for c in contributions 
        if c.get("contributor") == thr_addr
    ]
    
    return jsonify(contributions=user_contributions), 200
# EVM page
#
# Expose a simple UI for deploying and interacting with smart contracts via
# the Thronos EVM.  The actual EVM JSON-RPC endpoints are registered
# above via ``register_evm_routes``.  This route only renders the
# front-end interface (evm.html).
@app.route("/evm")
def evm_page():
    return render_template("evm.html")

@app.route("/playground")
def playground_page():
    """
    Render the DApp Playground interface for smart contract development.
    Users can write, compile, deploy, and test smart contracts.
    """
    return render_template("playground.html")

# Token listing & creation UI
@app.route("/tokens")
def tokens_page():
    """
    Render the custom token interface.  Users can view all issued
    tokens, see their own balances and mint new meme coins if
    authenticated.  Client-side code uses ``/api/v1/tokens`` and
    ``/api/v1/token_balances`` endpoints for data operations.
    """
    return render_template("tokens.html")

# Liquidity pools UI
@app.route("/pools")
def pools_page():
    """
    Render the liquidity pools interface.  Users can view all existing
    pools and create new ones by depositing pairs of tokens.  More
    advanced operations (adding/removing liquidity, swaps) may be
    integrated in future releases.  Client-side code uses
    ``/api/v1/pools`` along with the token registry for data.
    """
    return render_template("pools.html")

@app.route("/ai_packs")
def ai_packs_page():
    # Αν έχεις το ai_packs.html στο templates/
    return render_template("ai_packs.html")
    # Αν το βάλεις σε static/, τότε:
    # return send_from_directory(STATIC_DIR, "ai_packs.html")

# ─── ADMIN ROUTES (NEW) ────────────────────────────
@app.route("/admin/withdrawals")
def admin_withdrawals_page():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return "Forbidden", 403
    return render_template("admin_withdrawals.html", admin_secret=secret)

@app.route("/api/admin/withdrawals/list")
def api_admin_withdrawals_list():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="Forbidden"), 403
    return jsonify(load_json(WITHDRAWALS_FILE, [])), 200

@app.route("/api/admin/withdrawals/action", methods=["POST"])
def api_admin_withdrawals_action():
    data = request.get_json() or {}
    secret = data.get("secret")
    req_id = data.get("id")
    action = data.get("action") # 'paid' or 'rejected'
    
    if secret != ADMIN_SECRET:
        return jsonify(status="error", message="Forbidden"), 403
        
    withdrawals = load_json(WITHDRAWALS_FILE, [])
    found = False
    for w in withdrawals:
        if w["id"] == req_id:
            if w["status"] != "pending_admin_review":
                return jsonify(status="error", message="Already processed"), 400
            
            if action == "paid":
                w["status"] = "paid"
                w["processed_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            elif action == "rejected":
                w["status"] = "rejected"
                # Refund logic: Credit back the THR
                ledger = load_json(LEDGER_FILE, {})
                ledger[w["wallet"]] = round(float(ledger.get(w["wallet"], 0.0)) + float(w["thr_amount"]), 6)
                # Deduct from burn address (reverse the burn)
                ledger[BURN_ADDRESS] = round(max(0, float(ledger.get(BURN_ADDRESS, 0.0)) - float(w["thr_amount"])), 6)
                save_json(LEDGER_FILE, ledger)
                
                # Log Refund TX
                chain = load_json(CHAIN_FILE, [])
                tx = {
                    "type": "refund",
                    "from": "FIAT_GATEWAY",
                    "to": w["wallet"],
                    "amount": w["thr_amount"],
                    "reason": "Withdrawal Rejected",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    "tx_id": f"REFUND-{req_id}",
                    "status": "confirmed"
                }
                chain.append(tx)
                save_json(CHAIN_FILE, chain)
                update_last_block(tx, is_block=False)
            
            found = True
            break
            
    if found:
        save_json(WITHDRAWALS_FILE, withdrawals)
        return jsonify(status="success"), 200
    else:
        return jsonify(status="error", message="Request not found"), 404

# ─── ADDRESS MIGRATION ENDPOINT ─────────────────────────────────────────────

@app.route("/admin/migrate")
def admin_migrate_page():
    """Admin page for address migration UI"""
    return render_template("admin_migrate.html")

@app.route("/admin/migrate_addresses", methods=["POST"])
def migrate_addresses():
    """
    Migrates old timestamp-based THR addresses to new hex format.
    Preserves all balances, transactions, and pledge data.
    Admin only - requires ADMIN_SECRET.
    """
    data = request.get_json() or {}
    secret = data.get("secret", "")

    if secret != ADMIN_SECRET:
        return jsonify(error="Forbidden"), 403

    try:
        # Load all data
        pledges = load_json(PLEDGE_CHAIN, [])
        ledger = load_json(LEDGER_FILE, {})
        wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
        l2e_ledger = load_json(L2E_LEDGER_FILE, {})
        chain = load_json(CHAIN_FILE, [])

        # Create address mapping: old -> new
        address_mapping = {}
        migrated_pledges = []

        logger.info("Starting address migration...")

        # Step 1: Generate new addresses for all pledges
        for pledge in pledges:
            old_addr = pledge.get("thr_address", "")
            btc_addr = pledge.get("btc_address", "")

            # Skip if already in correct format
            if validate_thr_address(old_addr):
                migrated_pledges.append(pledge)
                continue

            # Extract timestamp from old address (THR1764439758289 -> 1764439758289)
            if old_addr.startswith("THR"):
                timestamp_part = old_addr[3:]
            else:
                # Fallback: use current time
                timestamp_part = str(int(time.time() * 1000))

            # Generate new hex address
            new_addr = generate_thr_address(btc_addr, timestamp_part)
            address_mapping[old_addr] = new_addr

            # Update pledge entry
            pledge["thr_address"] = new_addr
            pledge["old_address"] = old_addr  # Keep for reference
            pledge["migrated_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

            migrated_pledges.append(pledge)

            logger.info(f"Migrated {old_addr} -> {new_addr}")

        # Step 2: Update ledger balances
        new_ledger = {}
        for old_addr, balance in ledger.items():
            new_addr = address_mapping.get(old_addr, old_addr)
            new_ledger[new_addr] = balance

        # Step 3: Update WBTC ledger
        new_wbtc_ledger = {}
        for old_addr, balance in wbtc_ledger.items():
            new_addr = address_mapping.get(old_addr, old_addr)
            new_wbtc_ledger[new_addr] = balance

        # Step 4: Update L2E ledger
        new_l2e_ledger = {}
        for old_addr, balance in l2e_ledger.items():
            new_addr = address_mapping.get(old_addr, old_addr)
            new_l2e_ledger[new_addr] = balance

        # Step 5: Update blockchain transactions
        migrated_chain = []
        for entry in chain:
            if isinstance(entry, dict):
                # Update 'from' address
                if 'from' in entry and entry['from'] in address_mapping:
                    entry['from'] = address_mapping[entry['from']]

                # Update 'to' address
                if 'to' in entry and entry['to'] in address_mapping:
                    entry['to'] = address_mapping[entry['to']]

                # Update 'thr_address' (for blocks)
                if 'thr_address' in entry and entry['thr_address'] in address_mapping:
                    entry['thr_address'] = address_mapping[entry['thr_address']]

            migrated_chain.append(entry)

        # Step 6: Save all updated data
        save_json(PLEDGE_CHAIN, migrated_pledges)
        save_json(LEDGER_FILE, new_ledger)
        save_json(WBTC_LEDGER_FILE, new_wbtc_ledger)
        save_json(L2E_LEDGER_FILE, new_l2e_ledger)
        save_json(CHAIN_FILE, migrated_chain)

        # Update last_block.json if it exists
        last_block = load_json(LAST_BLOCK_FILE, {})
        if last_block:
            if last_block.get('thr_address') in address_mapping:
                last_block['thr_address'] = address_mapping[last_block['thr_address']]
            save_json(LAST_BLOCK_FILE, last_block)

        logger.info(f"Migration complete! Migrated {len(address_mapping)} addresses")

        return jsonify({
            "status": "success",
            "migrated_count": len(address_mapping),
            "address_mapping": address_mapping
        }), 200

    except Exception as e:
        logger.error(f"Migration error: {e}")
        return jsonify(error=str(e)), 500

# ─── PLEDGE REGENERATION ENDPOINT ───────────────────────────────────────────

@app.route("/admin/regenerate")
def admin_regenerate_page():
    """Admin page for pledge regeneration UI"""
    return render_template("admin_regenerate.html")

@app.route("/admin/regenerate_pledges", methods=["POST"])
def regenerate_pledges():
    """
    Regenerates pledge PDFs for all existing pledges with new hex addresses.
    Creates new PDFs with proper encryption and correct address format.
    Admin only - requires ADMIN_SECRET.
    """
    data = request.get_json() or {}
    secret = data.get("secret", "")

    if secret != ADMIN_SECRET:
        return jsonify(error="Forbidden"), 403

    try:
        pledges = load_json(PLEDGE_CHAIN, [])
        regenerated_count = 0
        results = []

        logger.info("Starting pledge regeneration...")

        for pledge in pledges:
            btc_addr = pledge.get("btc_address", "")
            thr_addr = pledge.get("thr_address", "")
            pledge_text = pledge.get("pledge_text", "I hereby pledge allegiance to the Thronos Chain.")
            passphrase = ""  # Passphrases aren't stored, user must remember

            # Check if address is already in hex format
            if not validate_thr_address(thr_addr):
                logger.warning(f"Pledge {btc_addr} has old address format: {thr_addr}")
                continue

            # Generate new send_seed and hashes
            send_seed = secrets.token_hex(16)
            send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()

            # If pledge had passphrase, we can't regenerate exact auth_hash
            # User must remember their passphrase
            if pledge.get("has_passphrase"):
                # Create placeholder that will work without passphrase
                auth_string = f"{send_seed}:auth"
            else:
                auth_string = f"{send_seed}:auth"

            send_auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()

            # Update pledge entry
            pledge["send_seed_hash"] = send_seed_hash
            pledge["send_auth_hash"] = send_auth_hash
            pledge["regenerated_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

            # Create new PDF with new credentials
            chain = load_json(CHAIN_FILE, [])
            height = len(chain)
            phash = pledge.get("pledge_hash", hashlib.sha256((btc_addr + pledge_text).encode()).hexdigest())

            pdf_name = create_secure_pdf_contract(
                btc_addr, pledge_text, thr_addr, phash, height, send_seed, CONTRACTS_DIR, passphrase
            )

            pledge["pdf_filename"] = pdf_name
            pledge["new_send_seed_available"] = True

            results.append({
                "btc_address": btc_addr,
                "thr_address": thr_addr,
                "pdf_filename": pdf_name,
                "send_seed": send_seed,
                "had_passphrase": pledge.get("has_passphrase", False)
            })

            regenerated_count += 1
            logger.info(f"Regenerated pledge for {thr_addr}")

        # Save updated pledges
        save_json(PLEDGE_CHAIN, pledges)

        logger.info(f"Pledge regeneration complete! Regenerated {regenerated_count} pledges")

        return jsonify({
            "status": "success",
            "regenerated_count": regenerated_count,
            "results": results,
            "warning": "Users with passphrases will need to re-set them for sending THR"
        }), 200

    except Exception as e:
        logger.error(f"Pledge regeneration error: {e}")
        return jsonify(error=str(e)), 500

# ─── AI ARCHITECT ROUTES (NEW) ──────────────────────────────────────────────

@app.route("/architect")
def architect_page():
    return render_template("architect.html")

@app.route("/api/ai_blueprints")
def api_ai_blueprints():
    """
    Returns list of available blueprints from data/ai_blueprints/
    """
    bp_dir = os.path.join(DATA_DIR, "ai_blueprints")
    if not os.path.exists(bp_dir):
        os.makedirs(bp_dir, exist_ok=True)
    
    blueprints = []
    try:
        for f in os.listdir(bp_dir):
            if f.endswith(".md") or f.endswith(".txt"):
                blueprints.append(f)
    except Exception as e:
        print("Error listing blueprints:", e)
        
    # Sort for consistency
    blueprints.sort()
    return jsonify({"blueprints": blueprints}), 200

@app.route("/api/architect_generate", methods=["POST"])
def api_architect_generate():
    """
    Thronos AI Architect:
    - Generates full project implementation based on blueprint + specs.
    - Returns [[FILE:...]] blocks.
    - Writes files to AI_FILES_DIR.
    """
    if not ai_agent:
        return jsonify(error="AI Agent not available"), 503

    data = request.get_json() or {}
    wallet      = (data.get("wallet") or "").strip()
    session_id  = (data.get("session_id") or "").strip() or None
    blueprint   = (data.get("blueprint") or "").strip()
    project_spec = (data.get("spec") or data.get("specs") or "").strip() # Handle both keys just in case
    model_key   = (data.get("model") or data.get("model_key") or "gpt-4o").strip()

    if not blueprint or not project_spec:
        return jsonify(error="Missing blueprint or spec"), 400

    # FIX 8: Require wallet for Architect (THR billing mode)
    if not wallet:
        return jsonify(error="Wallet required for Architect (THR billing)"), 400

    # Load blueprint
    bp_path = os.path.join(DATA_DIR, "ai_blueprints", blueprint)
    if not os.path.exists(bp_path):
        # Fallback: try to find it in the list if passed as name only
        bp_dir = os.path.join(DATA_DIR, "ai_blueprints")
        found = False
        if os.path.exists(bp_dir):
            for f in os.listdir(bp_dir):
                if f == blueprint:
                    bp_path = os.path.join(bp_dir, f)
                    found = True
                    break
        if not found:
             return jsonify(error="Blueprint not found"), 404

    try:
        with open(bp_path, "r", encoding="utf-8") as f:
            bp_text = f.read()
    except Exception as e:
        return jsonify(error=f"Cannot read blueprint: {e}"), 500

    # New FULL IMPLEMENTATION prompt
    prompt = (
        "Είσαι ο Κύριος Αρχιτέκτονας του Thronos.\\n"
        "Χτίζεις ΠΛΗΡΗ software projects (όχι μόνο skeletons).\\n"
        "Για κάθε αρχείο που παράγεις, γράφεις όσο πιο ολοκληρωμένο, λειτουργικό κώδικα γίνεται.\\n"
        "- Π.χ. αν υπάρχει login page, υλοποίησε πλήρη φόρμα, validation και fake auth flow.\\n"
        "- Αν υπάρχει API route, γράψε πλήρες handler με όλα τα πεδία.\\n"
        "- Αν υπάρχει API route, γράψε πλήρες handler με όλα τα πεδία.\\n"
        "- Αν υπάρχει database layer, βάλε πλήρη μοντέλα / helpers.\\n\\n"
        "ΠΡΟΤΥΠΟ ΕΞΟΔΟΥ:\\n"
        "Πρέπει να απαντάς ΜΟΝΟ με blocks της μορφής:\\n"
        "[[FILE:path/filename.ext]]\\n"
        "...περιεχόμενο αρχείου...\\n"
        "[[/FILE]]\\n\\n"
        "Μην εξηγήσεις, μην προσθέσεις κείμενο εκτός αρχείων.\\n\\n"
        "BLUEPRINT:\\n"
        f"{bp_text}\\n\\n"
        "PROJECT SPEC (τι θέλει ο χρήστης):\\n"
        f"{project_spec}\\n\\n"
        "Χτίσε ΟΛΑ τα βασικά αρχεία του project με ΠΛΗΡΗ υλοποίηση, όχι απλό σκελετό."
    )

    # Call AI
    # Note: server.py uses 'ai_agent' global instance
    # Pass session_id to maintain context if needed (though architect usually is one-shot, 
    # but user might refine in same session)
    raw = ai_agent.generate_response(prompt, wallet=wallet, model_key=model_key, session_id=session_id)

    if isinstance(raw, dict):
        full_text   = str(raw.get("response") or "")
        quantum_key = raw.get("quantum_key") or ai_agent.generate_quantum_key()
        status      = raw.get("status", "architect")
    else:
        full_text   = str(raw)
        quantum_key = ai_agent.generate_quantum_key()
        status      = "architect"

    # Extract files
    try:
        files, cleaned = extract_ai_files_from_text(full_text)
    except Exception as e:
        print("Architect file extraction error:", e)
        files = []
        cleaned = full_text

    # Log to corpus
    try:
        title = f"[ARCHITECT:{blueprint}] {project_spec[:80]}"
        enqueue_offline_corpus(wallet, title, full_text, files, session_id=session_id)
    except Exception as e:
        print("architect corpus error:", e)

    # FIX 8: Calculate Architect fee (base + variable)
    tokens_out = len(full_text.split())  # Rough token estimate (words)
    files_count = len(files) if files else 0
    architect_fee = billing.calculate_architect_fee(tokens_out=tokens_out, files_count=files_count, blueprint_complexity=1)

    # FIX 8: Charge THR (Architect billing mode - no credits)
    charge_success, charge_error, charge_telemetry = billing.charge_thr(
        wallet=wallet,
        amount=architect_fee,
        reason="architect_usage",
        product="architect",
        metadata={
            "blueprint": blueprint,
            "files_generated": files_count,
            "tokens_out": tokens_out,
            "model": model_key,
            "session_id": session_id
        }
    )

    if not charge_success:
        # Insufficient THR - return error
        return jsonify({
            "error": charge_error,
            "status": "insufficient_thr",
            "thr_available": charge_telemetry.get("thr_available", 0),
            "thr_needed": float(architect_fee)
        }), 402  # Payment Required

    # FIX 8: Grant credits reward (1 THR → 10 credits)
    reward_telemetry = billing.grant_credits_from_thr_spend(wallet, architect_fee)

    resp_files = []
    for f in files or []:
        if isinstance(f, dict):
            fname = f.get("filename") or f.get("name")
            fsize = f.get("size")
        else:
            fname = str(f or "").strip()
            fsize = None
        if not fname:
            continue
        resp_files.append({
            "filename": fname,
            "size": fsize,
            "url": f"/api/ai/generated/{fname}",
        })

    zip_url = None
    if resp_files:
        safe_bp = blueprint.replace("/", "_").replace("..", "_") or "bp"
        zip_name = f"architect_{safe_bp}_{int(time.time())}.zip"
        zip_path = os.path.join(AI_FILES_DIR, zip_name)
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in resp_files:
                    fp = os.path.join(AI_FILES_DIR, item["filename"])
                    if os.path.exists(fp):
                        zf.write(fp, arcname=item["filename"])
            zip_url = url_for("api_ai_generated_file", filename=zip_name, _external=False)
        except Exception as e:
            app.logger.error("Architect zip build failed: %s", e)

    return jsonify({
        "status": status,
        "quantum_key": quantum_key,
        "blueprint": blueprint,
        "response": cleaned,
        "files": resp_files,
        "zip_url": zip_url,
        "session_id": session_id,
        # FIX 8: Billing info
        "thr_spent": float(architect_fee),
        "credits_granted": reward_telemetry.get("credits_delta", 0),
        "billing_channel": "thr",
        "tx_id": charge_telemetry.get("tx_id"),
    }), 200


@app.route("/api/architect_download", methods=["POST"])
def api_architect_download():
    """
    Παίρνει λίστα filenames (όπως γυρίζει το /api/architect_generate)
    και επιστρέφει ZIP με τα αντίστοιχα αρχεία από το AI_FILES_DIR.
    Body:
      { "files": ["package.json", "pages_index.js", ...] }
      ή { "files": [ { "filename": "package.json" }, ... ] }
    """
    data = request.get_json(silent=True) or {}
    files_in = data.get("files") or []
    if not isinstance(files_in, list) or not files_in:
        return jsonify({"ok": False, "error": "no files provided"}), 400

    to_zip = []
    for item in files_in:
        if isinstance(item, dict):
            name = (item.get("filename") or "").strip()
        else:
            name = str(item or "").strip()
        if not name:
            continue
        safe_name = name.replace("..", "_").replace("/", "_").replace("\\", "_")
        path = os.path.join(AI_FILES_DIR, safe_name)
        if os.path.exists(path):
            to_zip.append((safe_name, path))

    if not to_zip:
        return jsonify({"ok": False, "error": "no valid files found"}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_name, path in to_zip:
            zf.write(path, arcname=safe_name)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="thronos_architecture.zip",
    )

# ─── RECOVERY FLOW ─────────────────────────────────
@app.route("/recovery")
def recovery_page():
    return render_template("recovery.html")

@app.route("/recover_submit", methods=["POST"])
def recover_submit():
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    passphrase = request.form.get("passphrase","").strip()
    if file.filename=="":
        return jsonify(error="No selected file"), 400
    if not passphrase:
        return jsonify(error="Passphrase is required"), 400
    filename = secure_filename(file.filename)
    temp_path = os.path.join(DATA_DIR, f"temp_{int(time.time())}_{filename}")
    try:
        file.save(temp_path)
        payload = decode_payload_from_image(temp_path, passphrase)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if payload:
            return jsonify(status="success", payload=payload), 200
        return jsonify(error="Failed to decode or decrypt."), 400
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify(error=f"Server error: {str(e)}"), 500


# ─── STATUS APIs ───────────────────────────────────
@app.route("/chain")
def get_chain():
    return jsonify(load_json(CHAIN_FILE, [])), 200

@app.route("/last_block")
def api_last_block():
    return jsonify(load_json(LAST_BLOCK_FILE, {})), 200

@app.route("/last_block_hash")
def last_block_hash():
    chain = load_chain_cached()
    blocks = get_reward_blocks()
    if blocks:
        last = blocks[-1]
        global_height = HEIGHT_OFFSET + len(blocks) - 1
        return jsonify(
            last_hash=last.get("block_hash", ""),
            height=global_height,
            timestamp=last.get("timestamp"),
        )
    return jsonify(last_hash="0"*64, height=-1, timestamp=None)

@app.route("/mining_info")
def mining_info():
    target = get_mining_target()
    nbits  = target_to_bits(target)

    chain  = load_chain_cached()
    blocks = get_reward_blocks()

    last_hash = blocks[-1].get("block_hash", "") if blocks else "0" * 64

    local_height   = len(blocks)               # πόσα blocks έχουμε στο αρχείο
    global_height  = HEIGHT_OFFSET + local_height  # block height με το offset
    reward         = calculate_reward(global_height)

    mempool_len = len(load_mempool())

    return jsonify({
        "target":        hex(target),
        "nbits":         hex(nbits),
        "difficulty_int": int(INITIAL_TARGET // target),
        "reward":        reward,
        "height":        global_height,
        "local_height":  local_height,
        "last_hash":     last_hash,
        "mempool":       mempool_len,
    }), 200

@app.route("/api/network_stats")
def network_stats():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain   = load_json(CHAIN_FILE, [])
    ledger  = load_json(LEDGER_FILE, {})

    pledge_count = len(pledges)

    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    block_count = HEIGHT_OFFSET + len(blocks)

    tx_count = len([
        t for t in chain
        if isinstance(t, dict) and t.get("type") in ("transfer", "service_payment", "ai_knowledge", "coinbase")
    ])

    burned     = float(ledger.get(BURN_ADDRESS, 0))
    ai_balance = float(ledger.get(AI_WALLET_ADDRESS, 0))
    total_supply = round(sum(float(v) for v in ledger.values()), 6)

    # pledge growth όπως πριν
    pledge_dates = {}
    for p in pledges:
        ts = p.get("timestamp", "").split(" ")[0]
        if not ts:
            continue
        pledge_dates[ts] = pledge_dates.get(ts, 0) + 1

    sorted_dates = sorted(pledge_dates.keys())
    cumulative   = []
    run = 0
    for d in sorted_dates:
        run += pledge_dates[d]
        cumulative.append({"date": d, "count": run})

    return jsonify({
        "pledge_count": pledge_count,
        "block_count":  block_count,
        "tx_count":     tx_count,
        "burned":       burned,
        "ai_balance":   ai_balance,
        "total_supply": total_supply,
        "pledge_growth": cumulative,
    })

# ─── WALLETS COUNT ─────────────────────────────────────────────────────

@app.route("/api/v1/wallets/count")
def wallets_count():
    """Return the count of unique wallets in the ledger"""
    ledger = load_json(LEDGER_FILE, {})
    # Count wallets with non-zero balance, excluding system addresses
    system_addresses = {BURN_ADDRESS, AI_WALLET_ADDRESS, "GENESIS", "SYSTEM"}
    wallet_count = sum(1 for addr, bal in ledger.items()
                       if addr not in system_addresses and float(bal) > 0)
    return jsonify({"count": wallet_count})

# ─── PEERS & HEARTBEAT ─────────────────────────────────────────────────────

def cleanup_expired_peers():
    """Remove peers that haven't sent heartbeat in PEER_TTL_SECONDS"""
    global active_peers
    now = _now_ts()
    expired = [peer_id for peer_id, data in active_peers.items()
               if now - data.get("last_seen", 0) > PEER_TTL_SECONDS]
    for peer_id in expired:
        del active_peers[peer_id]
    return len(expired)

@app.route("/api/peers/heartbeat", methods=["POST"])
def peers_heartbeat():
    """
    Replica nodes send heartbeat to master with their peer_id and URL.
    Master tracks active replicas with TTL of 60 seconds.
    """
    if NODE_ROLE != "master":
        return jsonify({"error": "Heartbeats only accepted on master node"}), 403

    data = request.get_json() or {}
    peer_id = data.get("peer_id")
    peer_url = data.get("url")

    if not peer_id:
        return jsonify({"error": "peer_id required"}), 400

    # Update peer tracking
    active_peers[peer_id] = {
        "last_seen": _now_ts(),
        "url": peer_url or "unknown",
        "node_role": "replica"
    }

    cleanup_expired_peers()

    return jsonify({
        "status": "ok",
        "peer_id": peer_id,
        "active_peers": len(active_peers),
        "ttl_seconds": PEER_TTL_SECONDS
    }), 200

@app.route("/api/network_live")
def network_live():
    chain  = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    mempool_len = len(load_mempool())

    window = 20
    avg_time = None
    if len(blocks) >= 2:
        tail = blocks[-min(window, len(blocks)):]
        try:
            t_fmt = "%Y-%m-%d %H:%M:%S UTC"
            t0 = datetime.strptime(tail[0]["timestamp"], t_fmt).timestamp()
            t1 = datetime.strptime(tail[-1]["timestamp"], t_fmt).timestamp()
            avg_time = (t1 - t0) / max(1, (len(tail) - 1))
        except Exception:
            avg_time = None

    target     = get_mining_target()
    difficulty = int(INITIAL_TARGET // target)
    hashrate   = None
    if avg_time and avg_time > 0:
        hashrate = int(difficulty * (2**32) / avg_time)

    block_count = HEIGHT_OFFSET + len(blocks)

    # Calculate active miners (unique miners in last 100 blocks)
    active_miners_window = 100
    recent_blocks = blocks[-min(active_miners_window, len(blocks)):]
    unique_miners = set()
    for block in recent_blocks:
        miner_addr = block.get("thr_address") or block.get("miner_address")
        if miner_addr:
            unique_miners.add(miner_addr)
    active_miners = len(unique_miners)

    # Active peers - use real heartbeat tracking from replicas
    cleanup_expired_peers()  # Remove stale peers
    active_peers_count = len(active_peers)

    return jsonify({
        "difficulty":          difficulty,
        "avg_block_time_sec":  avg_time,
        "est_hashrate_hs":     hashrate,
        "block_count":         block_count,
        "tx_count":            len(chain),
        "mempool":             mempool_len,
        "active_miners":       active_miners,
        "active_peers":        active_peers_count,
    })


def _current_chain_height() -> int:
    """Return current chain height (including HEIGHT_OFFSET)."""
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    return HEIGHT_OFFSET + len(blocks)


def _list_api_routes():
    """Return list of API routes under the configured base prefix."""
    routes = []
    for rule in app.url_map.iter_rules():
        if not str(rule).startswith(API_BASE_PREFIX):
            continue
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        routes.append({"rule": str(rule), "methods": methods})
    routes.sort(key=lambda r: r["rule"])
    return routes

@app.route("/api/mempool")
def api_mempool():
    return jsonify(load_mempool()), 200

@app.route("/api/blocks")
def api_blocks():
    return jsonify(get_blocks_for_viewer()), 200

@app.route("/api/transactions")
def api_transactions():
    """Return all transactions for the viewer including swaps"""
    return jsonify(get_transactions_for_viewer()), 200


@app.route("/api/health")
def api_health():
    """
    Lightweight health check with chain and version info.
    FIX 1: Extended with build info for deployment verification.
    """
    try:
        height = _current_chain_height()
    except Exception:
        height = 0

    # CRITICAL FIX #3: Get git commit from env vars (Railway, Vercel, etc) or git command
    git_commit = "unknown"
    checked_env = []

    # Try environment variables first (Railway, Vercel, etc)
    env_vars = ["RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"]
    for env_var in env_vars:
        checked_env.append(env_var)
        commit_sha = os.getenv(env_var)
        if commit_sha:
            # Take first 7 chars for short hash
            git_commit = commit_sha[:7] if len(commit_sha) > 7 else commit_sha
            break

    # Fallback: try git command (for local dev)
    if git_commit == "unknown":
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass

    # FIX 1: Build metadata
    build_info = {
        "git_commit": git_commit,
        "checked_env": checked_env,  # Show which env vars we checked
        "build_time": os.path.getmtime(__file__) if os.path.exists(__file__) else None,
        "DATA_DIR": os.getenv("DATA_DIR", "/app/data"),
        "node_role": os.getenv("NODE_ROLE", "standalone"),
        "degraded_mode_enabled": True  # Always use degraded mode patterns
    }

    # FIX 1: Env presence check (names only, no secrets)
    env_present = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "OPENAI_KEY": bool(os.getenv("OPENAI_KEY")),
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
        "DATA_DIR": bool(os.getenv("DATA_DIR"))
    }

    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "chain_height": height,
        "api_base": API_BASE_PREFIX,
        "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "build": build_info,
        "env_present": env_present
    }), 200


@app.route("/api/routes")
def api_routes_listing():
    """Return a JSON listing of available API routes under the contract base."""
    return jsonify({"routes": _list_api_routes()}), 200


# ─── NEW SERVICES APIs ─────────────────────────────
@app.route("/api/bridge/data")
def bridge_data():
    return jsonify(load_json(WATCHER_LEDGER_FILE, [])), 200


def _load_bridge_txs():
    txs = load_json(WATCHER_LEDGER_FILE, [])
    if isinstance(txs, dict):
        if "txs" in txs:
            txs = txs.get("txs", [])
        elif "transactions" in txs:
            txs = txs.get("transactions", [])
        else:
            txs = list(txs.values())
    return txs if isinstance(txs, list) else []


@app.route("/api/bridge/txs")
def api_bridge_txs():
    """Return recorded bridge transactions (alias for watcher ledger)."""
    return jsonify(txs=_load_bridge_txs()), 200


@app.route("/api/bridge/stats")
def api_bridge_stats():
    """Return basic bridge statistics for UI dashboards."""
    txs = _load_bridge_txs()
    total_btc = 0.0
    total_thr = 0.0
    pending = 0
    for tx in txs:
        try:
            total_btc += float(tx.get("btc_amount", tx.get("btc", 0.0)))
            total_thr += float(tx.get("thr_amount", tx.get("thr", 0.0)))
        except Exception:
            pass
        status = str(tx.get("status", "")).lower()
        if status in {"pending", "processing"}:
            pending += 1
    return jsonify({
        "txs": len(txs),
        "total_btc": round(total_btc, 8),
        "total_thr": round(total_thr, 6),
        "pending": pending,
        "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }), 200


@app.route("/api/bridge/status")
def api_bridge_status():
    """
    Return operational status of the bridge.

    Returns:
        - ok: boolean indicating if bridge is operational
        - mode: "disabled" | "manual" | "beta" | "live"
        - last_sync: timestamp of last sync
        - reserves: current bridge reserves (if applicable)
        - notes: human-readable status message
    """
    txs = _load_bridge_txs()

    # Determine mode based on configuration and endpoint availability
    # Currently the burn endpoint returns 501, so bridge is in "manual" mode
    mode = os.getenv("BRIDGE_MODE", "manual")
    notes = "Bitcoin bridge is in manual mode. Automated bridging is coming soon. Check roadmap for updates."

    # Calculate basic stats
    last_tx_time = None
    if txs:
        try:
            # Try to get the most recent transaction timestamp
            for tx in reversed(txs):
                if "timestamp" in tx:
                    last_tx_time = tx["timestamp"]
                    break
        except Exception:
            pass

    return jsonify({
        "ok": mode in {"beta", "live"},
        "mode": mode,
        "last_sync": last_tx_time or datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "reserves": {
            "btc": 0.0,  # Would be calculated from actual reserve wallet
            "thr": 0.0   # Would be calculated from bridge contract
        },
        "notes": notes,
        "endpoints": {
            "stats": "/api/bridge/stats",
            "history": "/api/bridge/history/<address>",
            "burn": "disabled"  # Currently returns 501
        }
    }), 200


@app.route("/api/bridge/history/<address>")
def api_bridge_history(address):
    """
    Return bridge history for a given Thronos / BTC address.

    The frontend calls this to show the user's recent bridge activity.
    We keep this very lightweight and tolerant to older records.
    """
    txs = _load_bridge_txs()
    norm = (address or "").strip()
    history = []
    for tx in txs:
        try:
            # Accept a few alternate field names so old records still match
            candidates = [
                tx.get("from_address"),
                tx.get("to_address"),
                tx.get("wallet"),
                tx.get("from"),
                tx.get("to"),
            ]
            if norm and any(c and str(c).strip() == norm for c in candidates):
                history.append(tx)
        except Exception:
            continue

    # Newest first, if timestamps exist
    try:
        history.sort(key=lambda t: t.get("timestamp", 0), reverse=True)
    except Exception:
        pass

    return jsonify({"address": norm, "history": history}), 200

@app.route("/api/bridge/burn", methods=["POST"])
def api_bridge_burn_alias():
    """Stub burn endpoint to keep client compatibility when burn flow is disabled."""
    return jsonify({"ok": False, "message": "Bridge burn flow is not enabled on this node."}), 501

@app.route("/api/iot/data")
def iot_data():
    data = load_json(IOT_DATA_FILE, [])
    return jsonify(data if data else []), 200

@app.route("/api/iot/submit", methods=["POST"])
def iot_submit():
    if "file" not in request.files:
        return jsonify(error="No file uploaded"), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify(error="No file selected"), 400
    try:
        filename=secure_filename(file.filename)
        temp_path=os.path.join(UPLOADS_DIR,f"iot_temp_{int(time.time())}_{filename}")
        file.save(temp_path)
        data=decode_iot_steganography(temp_path)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if not data:
            return jsonify(error="Failed to decode steganography"),400
        if "vehicle_id" not in data:
            return jsonify(error="Invalid data format"),400
        iot_list=load_json(IOT_DATA_FILE,[])
        iot_list=[v for v in iot_list if v.get("vehicle_id")!=data["vehicle_id"]]
        iot_list.append(data)
        if len(iot_list)>100:
            iot_list=iot_list[-100:]
        save_json(IOT_DATA_FILE,iot_list)
        print(f"🚗 IoT Update: {data['vehicle_id']} | Odo: {data.get('odometer')}")
        return jsonify(status="success", vehicle_id=data["vehicle_id"]),200
    except Exception as e:
        print("IoT Submit Error:",e)
        return jsonify(error=str(e)),500

@app.route("/api/iot/autonomous_request", methods=["POST"])
def iot_autonomous_request():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    amount = data.get("amount",0)
    if not wallet or amount<=0:
        return jsonify(status="denied",message="Invalid request"),400
    ledger=load_json(LEDGER_FILE,{})
    balance=float(ledger.get(wallet,0.0))
    if balance<amount:
        return jsonify(status="denied",message="Insufficient THR funds"),400
    ledger[wallet]=round(balance-amount,6)
    ledger[AI_WALLET_ADDRESS]=round(ledger.get(AI_WALLET_ADDRESS,0.0)+amount,6)
    save_json(LEDGER_FILE,ledger)
    chain=load_json(CHAIN_FILE,[])
    tx={
        "type":"service_payment",
        "service":"AI_AUTOPILOT",
        "from":wallet,
        "to":AI_WALLET_ADDRESS,
        "amount":amount,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id":f"SRV-{len(chain)}-{int(time.time())}"
    }
    chain.append(tx)
    save_json(CHAIN_FILE,chain)
    update_last_block(tx,is_block=False)
    print(f"🤖 AI Autopilot Activated for {wallet}. Payment: {amount} THR")
    return jsonify(status="granted", message="AI Driver Activated"),200

# ─── IOT PARKING API (NEW) ─────────────────────────
@app.route("/api/iot/parking", methods=["GET"])
def api_iot_parking():
    """
    Returns the current state of parking spots.
    If file doesn't exist, init with random data.
    """
    if not os.path.exists(IOT_PARKING_FILE):
        # Init random spots
        spots = []
        for i in range(12):
            spots.append({
                "id": f"P-{101+i}",
                "status": "free" if random.random() > 0.3 else "occupied",
                "reservedBy": None
            })
        save_json(IOT_PARKING_FILE, spots)
    
    return jsonify(load_json(IOT_PARKING_FILE, [])), 200

@app.route("/api/iot/reserve", methods=["POST"])
def api_iot_reserve():
    """
    Reserves a spot. Requires payment (handled via send_thr logic usually, 
    but here we can just update state if payment verified or trust client for MVP simulation).
    Ideally, client calls send_thr, then calls this with tx_id to prove payment.
    For simplicity/simulation, we just update state.
    """
    data = request.get_json() or {}
    spot_id = data.get("spot_id")
    wallet = data.get("wallet")
    
    if not spot_id or not wallet:
        return jsonify(error="Missing fields"), 400
        
    spots = load_json(IOT_PARKING_FILE, [])
    found = False
    for s in spots:
        if s["id"] == spot_id:
            if s["status"] != "free":
                return jsonify(error="Spot not free"), 400
            s["status"] = "reserved"
            s["reservedBy"] = wallet
            found = True
            break
            
    if found:
        save_json(IOT_PARKING_FILE, spots)
        return jsonify(status="success"), 200
    else:
        return jsonify(error="Spot not found"), 404


# ─── VOTING API (Crypto Hunters Feature Voting) ─────────────────────────────
@app.route("/api/voting/polls", methods=["GET"])
def api_voting_polls():
    """Get all active voting polls."""
    voting_data = load_voting()
    return jsonify(voting_data.get("polls", [])), 200

@app.route("/api/voting/vote", methods=["POST"])
def api_voting_vote():
    """
    Submit a vote for a feature.
    Expected JSON: {"poll_id": "feature_pvp", "wallet": "THR..."}
    """
    data = request.get_json() or {}
    poll_id = data.get("poll_id")
    wallet = data.get("wallet")

    if not poll_id:
        return jsonify(error="poll_id required"), 400

    # Guest voting is allowed, but wallet voting prevents duplicate votes
    voting_data = load_voting()

    # Check if wallet already voted for this poll
    vote_key = f"{poll_id}:{wallet}" if wallet else f"{poll_id}:guest_{secrets.token_hex(8)}"

    if wallet and vote_key in voting_data.get("votes", {}):
        return jsonify(error="Already voted", status="duplicate"), 400

    # Find and increment the poll
    poll_found = False
    for poll in voting_data.get("polls", []):
        if poll["id"] == poll_id:
            poll["votes"] = poll.get("votes", 0) + 1
            poll_found = True
            break

    if not poll_found:
        return jsonify(error="Poll not found"), 404

    # Record the vote
    if "votes" not in voting_data:
        voting_data["votes"] = {}

    voting_data["votes"][vote_key] = {
        "timestamp": datetime.utcnow().isoformat(),
        "wallet": wallet or "guest"
    }

    save_voting(voting_data)

    return jsonify(status="success", message="Vote recorded"), 200

@app.route("/api/voting/results", methods=["GET"])
def api_voting_results():
    """Get voting results with total counts."""
    voting_data = load_voting()
    polls = voting_data.get("polls", [])

    results = []
    for poll in polls:
        results.append({
            "id": poll["id"],
            "title": poll["title"],
            "description": poll["description"],
            "votes": poll.get("votes", 0)
        })

    # Sort by votes descending
    results.sort(key=lambda x: x["votes"], reverse=True)

    return jsonify(results), 200


# ─── QUANTUM CHAT API (ενιαίο AI + αρχεία + offline corpus) ─────────────────
@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Unified AI chat endpoint με credits + sessions.

    - Αν ο χρήστης έχει δηλώσει wallet, καίει AI credits από το ai_credits.json
    - Αν δεν έχει wallet, δουλεύει ως demo (infinite)
    - Αν έχει wallet αλλά 0 credits, δεν προχωρά σε κλήση AI
    - Κάθε μήνυμα γράφεται στο ai_offline_corpus.json με session_id
    """
    if not ai_agent:
        return jsonify(error="AI Agent not available"), 503

    data = request.get_json() or {}
    msg = (data.get("message") or "").strip()
    wallet = (data.get("wallet") or "").strip()  # MOVED HERE - must be before attachments!
    session_id = (data.get("session_id") or "").strip() or None
    model_key = (data.get("model_key") or "").strip() or None
    attachments = data.get("attachments") or data.get("attachment_ids") or []
    ai_credits_spent = 0.0

    if session_id:
        ensure_session_exists(session_id, wallet)
        try:
            register_session({"session_id": session_id, "user_wallet": wallet or None})
        except Exception:
            pass

    # Attachments are file_ids previously uploaded via /api/ai/files/upload
    if attachments:
        idx = load_upload_index()
        parts = []
        files_processed = []
        files_skipped = []

        for fid in attachments:
            meta = idx.get(fid)
            if not meta:
                files_skipped.append(f"{fid} (not found in index)")
                logger.warning(f"File {fid} not found in upload index")
                continue

            # basic ownership check: if wallet exists, enforce wallet match; else enforce guest id
            if wallet and meta.get("wallet") and meta.get("wallet") != wallet:
                files_skipped.append(f"{fid} (ownership mismatch)")
                logger.warning(f"File {fid} ownership mismatch: {meta.get('wallet')} != {wallet}")
                continue
            if (not wallet) and meta.get("guest_id") and meta.get("guest_id") != get_or_set_guest_id():
                files_skipped.append(f"{fid} (guest mismatch)")
                logger.warning(f"File {fid} guest mismatch")
                continue

            # Read file content
            file_path = meta.get("path", "")
            if not file_path or not os.path.exists(file_path):
                files_skipped.append(f"{fid} (file not found on disk)")
                logger.error(f"File {fid} path not found: {file_path}")
                continue

            text = read_text_file_for_prompt(file_path)
            filename = meta.get("filename", "unknown")
            parts.append(f"\n\n[📎 Attachment: {filename} | ID: {fid}]\n{text}")
            files_processed.append(filename)
            logger.info(f"Successfully attached file {filename} ({fid}) to chat message")

        if parts:
            msg = msg + "".join(parts)
            logger.info(f"Processed {len(files_processed)} attachments: {', '.join(files_processed)}")

        if files_skipped:
            logger.warning(f"Skipped {len(files_skipped)} attachments: {', '.join(files_skipped)}")

    if not msg:
        return jsonify(error="Message required"), 400

    # --- FIX 8: Credits check (Chat billing mode) ---
    credits_value = None
    if wallet:
        # Check credits availability (don't deduct yet - wait for successful AI call)
        credits_map = load_ai_credits()
        try:
            credits_value = int(credits_map.get(wallet, 0) or 0)
        except (TypeError, ValueError):
            credits_value = 0

        if credits_value <= 0:
            warning_text = (
                "Δεν έχεις άλλα Quantum credits γι' αυτό το THR wallet.\\n"
                "Πήγαινε στη σελίδα AI Packs και αγόρασε πακέτο για να συνεχίσεις."
            )
            return jsonify(
                response=warning_text,
                quantum_key=ai_agent.generate_quantum_key(),
                status="no_credits",
                wallet=wallet,
                credits=0,
                files=[],
                session_id=session_id,
            ), 200
    else:
        # No wallet supplied: treat this as a free demo chat.  Look up how
        # many messages have already been consumed for this session.  Once
        # the limit is reached, deny further requests until the user
        # supplies a wallet address.
        demo_key = session_id or "default"
        counters = load_ai_free_usage()
        used = int(counters.get(demo_key, 0))
        if used >= AI_FREE_MESSAGES_LIMIT:
            warning_text = (
                "Έχεις εξαντλήσει το όριο των δωρεάν μηνυμάτων χωρίς THR wallet.\\n"
                "Σύνδεσε ένα πορτοφόλι THR για να συνεχίσεις ή αγόρασε AI pack."
            )
            return jsonify(
                response=warning_text,
                quantum_key=ai_agent.generate_quantum_key(),
                status="no_credits",
                wallet="",
                credits=0,
                files=[],
                session_id=session_id,
            ), 200
        # Increment the counter and persist.  This ensures each demo call
        # counts towards the free limit.
        counters[demo_key] = used + 1
        save_ai_free_usage(counters)

    # --- Build context for conversation memory ---
    # To provide better continuity between messages, construct a short context
    # by loading the last few exchanges from the offline corpus for this
    # session.  Each entry in the corpus stores the original user prompt
    # and the AI response.  We interleave these into a list of
    # user/assistant messages and then take the N most recent.  The
    # context is flattened into a single string with role prefixes so
    # downstream providers receive a coherent history.  Limiting to 10
    # messages prevents excessively long prompts that could exhaust API
    # quotas.
    try:
        history_limit = 10
        # Collect past messages as simple dicts of {role, content}
        context_messages = []
        corpus = load_json(AI_CORPUS_FILE, []) or []
        # Determine the session identifier used in the corpus ("default" when empty)
        sid = session_id or "default"
        for entry in corpus:
            # Filter by wallet if provided
            if wallet and (entry.get("wallet") != wallet):
                continue
            # Filter by session id
            if (entry.get("session_id") or "default") != sid:
                continue
            # Append user prompt and assistant response in the order they were stored
            prompt_txt = entry.get("prompt", "")
            if prompt_txt:
                context_messages.append({"role": "user", "content": prompt_txt})
            resp_txt = entry.get("response", "")
            if resp_txt:
                context_messages.append({"role": "assistant", "content": resp_txt})
        # Only keep the most recent N messages
        context_messages = context_messages[-history_limit:]
        # Flatten into a string with role tags
        context_str_parts = []
        for m in context_messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            # Prepend role for clarity (capitalize the first letter)
            context_str_parts.append(f"{role.capitalize()}: {content}\n\n")
        context_str = "".join(context_str_parts)
    except Exception:
        # Fallback to no context on errors
        context_str = ""
    # Prepend the context to the current message.  The role for the
    # current user is explicitly labelled as "User" to distinguish it
    # from previous messages.  Any attachments have already been
    # appended to ``msg`` above.
    full_prompt = f"{context_str}User: {msg}" if context_str else msg

    # --- Κλήση στον ThronosAI provider ---
    # Pass model_key AND session_id to generate_response
    call_started = time.time()
    raw = ai_agent.generate_response(full_prompt, wallet=wallet, model_key=model_key, session_id=session_id)
    latency_ms = int((time.time() - call_started) * 1000)

    if isinstance(raw, dict):
        full_text = str(raw.get("response") or "")
        quantum_key = raw.get("quantum_key") or ai_agent.generate_quantum_key()
        status = raw.get("status", "secure")
        provider = raw.get("provider", "unknown")
        model = raw.get("model", "unknown")
    else:
        full_text = str(raw)
        quantum_key = ai_agent.generate_quantum_key()
        status = "secure"
        provider = "unknown"
        model = "unknown"

    # --- FILE blocks -> αρχεία ---
    try:
        files, cleaned = extract_ai_files_from_text(full_text)
    except Exception as e:
        print("AI file extraction error:", e)
        files = []
        cleaned = full_text

    # --- Offline corpus + sessions ---
    try:
        enqueue_offline_corpus(wallet, msg, full_text, files, session_id=session_id)
    except Exception as e:
        print("offline corpus enqueue error:", e)

    # --- FIX 8: Consume credits (Chat billing mode - no THR) ---
    if wallet:
        # Use billing module (clean separation, telemetry, cross-charge guard)
        success, error_msg, telemetry = billing.consume_credits(wallet, AI_CREDIT_COST_PER_MSG, product="chat")
        if not success:
            # This shouldn't happen (already checked above), but handle gracefully
            logger.error(f"Credits consumption failed after AI call: {error_msg}")
            credits_for_frontend = 0
            ai_credits_spent = 0.0
        else:
            credits_for_frontend = telemetry.get("credits_after", 0)
            ai_credits_spent = abs(telemetry.get("credits_delta", 0))
    else:
        # For demo sessions, report remaining free messages.  This
        # communicates to the user how many additional messages they may
        # send before needing to attach a wallet.  Note: the counter was
        # incremented above, so we subtract from the limit.
        try:
            counters = load_ai_free_usage()
            demo_key = session_id or "default"
            used_now = int(counters.get(demo_key, 0))
            credits_for_frontend = max(0, AI_FREE_MESSAGES_LIMIT - used_now)
        except Exception:
            credits_for_frontend = "infinite"
        ai_credits_spent = 0.0

    resp_files = []
    for f in files or []:
        if isinstance(f, dict):
            fname = f.get("filename") or f.get("name")
            fsize = f.get("size")
        else:
            fname = str(f or "").strip()
            fsize = None
        if not fname:
            continue
        resp_files.append({
            "filename": fname,
            "size": fsize,
            "url": f"/api/ai/generated/{fname}",
        })

    resp = {
        "response": cleaned,
        "quantum_key": quantum_key,
        "status": status,
        "provider": provider,
        "model": model,
        "wallet": wallet,
        "files": resp_files,
        "credits": credits_for_frontend,
        "session_id": session_id,
        "routing": None,
        "task_type": None,
    }

    routing_meta = raw.get("routing") if isinstance(raw, dict) else None
    task_type_meta = raw.get("task_type") if isinstance(raw, dict) else None
    hallucination_flags = raw.get("hallucination_flags") if isinstance(raw, dict) else []
    user_rating = raw.get("user_rating") if isinstance(raw, dict) else None

    resp["routing"] = routing_meta
    resp["task_type"] = task_type_meta

    try:
        interaction_entry = record_ai_interaction(
            session_id=session_id,
            user_wallet=wallet or None,
            provider=provider,
            model=model,
            prompt=full_prompt,
            output=full_text,
            tokens_input=len(full_prompt.split()),
            tokens_output=len(full_text.split()),
            cost_usd=0.0,
            latency_ms=latency_ms,
            ai_credits_spent=ai_credits_spent,
            feedback=None,
            metadata={"status": status, "task_type": task_type_meta, "routing": routing_meta},
            success=_status_is_success(status),
            task_type=task_type_meta,
            routing=routing_meta,
            hallucination_flags=hallucination_flags or [],
            user_rating=user_rating,
        )
    except Exception:
        logger.exception("Failed to record AI interaction")
        interaction_entry = None

    if ai_scorer and interaction_entry and interaction_entry.get("id"):
        try:
            scoring = ai_scorer.score_interaction(full_prompt, full_text)
            ledger_log_score(
                interaction_id=interaction_entry.get("id"),
                quality_score=scoring.get("quality_score", 0.0),
                safety_score=scoring.get("safety_score", 0.0),
                domain_label=scoring.get("domain_label"),
                model_decision=scoring.get("routing_label"),
                human_feedback=None,
            )
            resp["score"] = scoring
        except Exception:
            logger.exception("Failed to append AI score")
    return jsonify(resp), 200


@app.route("/api/v1/ai/log", methods=["POST"])
def api_ai_log_v1():
    if not _authorized_logging_request(request):
        return jsonify(error="Forbidden"), 403

    data = request.get_json() or {}
    provider_id = data.get("provider_id") or data.get("provider")
    model = data.get("model") or ""
    if not provider_id:
        return jsonify(error="provider_id is required"), 400

    prompt_text = data.get("prompt") or data.get("prompt_text") or ""
    response_text = data.get("response") or data.get("response_text") or ""
    session_id = data.get("session_id") or data.get("session")
    if session_id:
        try:
            register_session({"session_id": session_id, "user_wallet": data.get("user_wallet") or data.get("wallet")})
        except Exception:
            pass

    if data.get("provider_info"):
        try:
            register_provider(data.get("provider_info"))
        except Exception:
            pass

    entry = ledger_log_interaction(
        session_id=session_id,
        provider_id=provider_id,
        prompt_text=prompt_text,
        response_text=response_text,
        model=model,
        tokens_in=int(data.get("tokens_in") or data.get("tokens_input") or 0),
        tokens_out=int(data.get("tokens_out") or data.get("tokens_output") or 0),
        latency_ms=int(data.get("latency_ms") or data.get("latency") or 0),
        cost_est=float(data.get("cost_est") or data.get("cost_usd") or 0.0),
        user_wallet=data.get("user_wallet") or data.get("wallet"),
        metadata=data.get("metadata") or {},
    )

    return jsonify(status="ok", interaction=entry), 201


@app.route("/api/v1/ai/score", methods=["POST"])
def api_ai_score_v1():
    if not _authorized_logging_request(request):
        return jsonify(error="Forbidden"), 403

    data = request.get_json() or {}
    interaction_id = data.get("interaction_id")
    if not interaction_id:
        return jsonify(error="interaction_id is required"), 400

    score_entry = ledger_log_score(
        interaction_id=interaction_id,
        quality_score=float(data.get("quality_score") or 0.0),
        safety_score=float(data.get("safety_score") or 0.0),
        domain_label=data.get("domain_label"),
        model_decision=data.get("model_decision"),
        human_feedback=data.get("human_feedback"),
    )

    return jsonify(status="ok", score=score_entry), 201


@app.route(f"{API_BASE_PREFIX}/ai/interactions", methods=["GET"])
def api_ai_interactions_list():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="Forbidden"), 403

    provider = request.args.get("provider") or None
    model = request.args.get("model") or None
    wallet = request.args.get("wallet") or None
    try:
        from_ts = int(request.args.get("from_ts")) if request.args.get("from_ts") else None
    except Exception:
        from_ts = None
    try:
        to_ts = int(request.args.get("to_ts")) if request.args.get("to_ts") else None
    except Exception:
        to_ts = None

    try:
        limit = min(500, max(1, int(request.args.get("limit", 100))))
    except Exception:
        limit = 100
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except Exception:
        offset = 0

    interactions = load_ai_interactions()
    filtered = _filter_ai_interactions(
        interactions,
        provider=provider,
        model=model,
        wallet=wallet,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    sliced = filtered[offset : offset + limit]
    return jsonify(total=len(filtered), interactions=sliced), 200


@app.route(f"{API_BASE_PREFIX}/ai/metrics/summary", methods=["GET"])
def api_ai_metrics_summary():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="Forbidden"), 403

    provider = request.args.get("provider") or None
    model = request.args.get("model") or None
    wallet = request.args.get("wallet") or None
    try:
        from_ts = int(request.args.get("from_ts")) if request.args.get("from_ts") else None
    except Exception:
        from_ts = None
    try:
        to_ts = int(request.args.get("to_ts")) if request.args.get("to_ts") else None
    except Exception:
        to_ts = None

    interactions = load_ai_interactions()
    filtered = _filter_ai_interactions(
        interactions,
        provider=provider,
        model=model,
        wallet=wallet,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    return jsonify(_summarize_ai_metrics(filtered)), 200


@app.route("/api/ai/metrics", methods=["GET"])
def api_ai_metrics_public():
    provider = request.args.get("provider") or None
    model = request.args.get("model") or None
    wallet = request.args.get("wallet") or None
    try:
        from_ts = int(request.args.get("from_ts")) if request.args.get("from_ts") else None
    except Exception:
        from_ts = None
    try:
        to_ts = int(request.args.get("to_ts")) if request.args.get("to_ts") else None
    except Exception:
        to_ts = None

    interactions = load_ai_interactions()
    filtered = _filter_ai_interactions(
        interactions,
        provider=provider,
        model=model,
        wallet=wallet,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    return jsonify({
        "models": _aggregate_model_metrics(filtered),
        "updated_at": int(time.time() * 1000),
    }), 200


@app.route(f"{API_BASE_PREFIX}/ai/interactions/<interaction_id>/feedback", methods=["POST"])
def api_ai_interactions_feedback(interaction_id: str):
    data = request.get_json() or {}
    raw_score = data.get("score")
    try:
        score_val = int(raw_score) if raw_score is not None else None
    except Exception:
        score_val = None

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags if t is not None]

    interactions = load_ai_interactions()
    updated = False
    for entry in interactions:
        if entry.get("id") == interaction_id:
            entry["feedback"] = {"score": score_val, "tags": tags}
            updated = True
            break

    if not updated:
        return jsonify(error="Not found"), 404

    save_ai_interactions(interactions)
    return jsonify(status="ok", feedback={"score": score_val, "tags": tags}), 200

@app.route("/api/upload_training_data", methods=["POST"])
def api_upload_training_data():
    """
    Επιτρέπει το upload αρχείων για 'εκπαίδευση' ή εμπλουτισμό του corpus.
    """
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    wallet = request.form.get("wallet", "").strip()

    if file.filename == "":
        return jsonify(error="No selected file"), 400

    try:
        filename = secure_filename(file.filename)
        # Προσθήκη timestamp για μοναδικότητα
        safe_name = f"{int(time.time())}_{filename}"
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        
        file.save(file_path)
        
        # Καταγραφή στο offline corpus
        # Φτιάχνουμε μια δομή που να ταιριάζει με το enqueue_offline_corpus
        file_obj = {"filename": safe_name}
        enqueue_offline_corpus(wallet, "[System] Upload Training Data", f"File uploaded: {safe_name}", [file_obj])

        print(f"📂 AI Training Data Uploaded: {safe_name} by {wallet}")
        return jsonify(status="success", filename=safe_name, message="File uploaded to AI corpus"), 200

    except Exception as e:
        print("Upload Error:", e)
        return jsonify(error=str(e)), 500


@app.route("/api/ai_upload", methods=["POST"])
def api_ai_upload():
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    wallet = request.form.get("wallet", "").strip()
    session_id = (request.form.get("session_id") or "").strip() or None

    if file.filename == "":
        return jsonify(error="No selected file"), 400

    try:
        filename = secure_filename(file.filename)
        safe_name = f"{int(time.time())}_{filename}"
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        file.save(file_path)

        file_obj = {"filename": safe_name}
        enqueue_offline_corpus(
            wallet,
            "[System] Upload Training Data",
            f"File uploaded: {safe_name}",
            [file_obj],
            session_id=session_id,
        )

        print(f"📂 AI Training Data Uploaded: {safe_name} by {wallet}")
        return jsonify(status="success", filename=safe_name, message="File uploaded to AI corpus"), 200

    except Exception as e:
        print("Upload Error:", e)
        return jsonify(error=str(e)), 500


# ─── AI PACKS API ──────────────────────────────────────────────────────────────

@app.route("/api/ai_credits", methods=["GET"])
def api_ai_credits():
    """
    Επιστρέφει τα διαθέσιμα AI credits για ένα wallet.
    Αν δεν δοθεί wallet, θεωρούμε demo / infinite.
    """
    wallet = (request.args.get("wallet") or "").strip()
    if not wallet:
        # no wallet => do not expose server-side sessions
        gid = get_or_set_guest_id()
        resp = jsonify({"sessions": [], "mode": "guest"})
        resp.set_cookie(GUEST_COOKIE_NAME, gid, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp, 200
    if not wallet:
        gid = get_or_set_guest_id()
        remaining = guest_remaining_free_messages(gid)
        resp = jsonify({"mode": "guest", "credits": remaining, "max_free_messages": GUEST_MAX_FREE_MESSAGES})
        # set cookie so we can track remaining free questions
        resp.set_cookie(GUEST_COOKIE_NAME, gid, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp, 200

    credits_map = load_ai_credits()
    try:
        value = int(credits_map.get(wallet, 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return jsonify({"wallet": wallet, "credits": value}), 200


@app.route("/api/ai/files/upload", methods=["POST"])
def api_ai_files_upload():
    """
    Multipart upload endpoint used by /chat:
      - field: files (one or many)
      - form: wallet (optional), session_id (optional), purpose (optional)
    Returns:
      { ok: true, files: [{id, name, size, mimetype, sha256}] }
    """
    try:
        # accept either files[] or files
        files = (request.files.getlist("files") or request.files.getlist("files[]") or request.files.getlist("file"))
        if not files:
            return jsonify(ok=False, error="No files uploaded. Use multipart field 'files'."), 400

        wallet = (request.form.get("wallet") or "").strip()
        session_id = (request.form.get("session_id") or "").strip()
        purpose = (request.form.get("purpose") or "chat").strip()

        # Get guest_id for non-wallet users (ownership tracking)
        guest_id = get_or_set_guest_id() if not wallet else None

        os.makedirs(AI_UPLOADS_DIR, exist_ok=True)

        uploaded = []
        for fs in files:
            if not fs or not getattr(fs, "filename", ""):
                continue

            original_name = secure_filename(fs.filename)
            # keep original extension when possible
            ext = os.path.splitext(original_name)[1][:16]
            ext = re.sub(r"[^a-zA-Z0-9.]", "", ext)

            blob = fs.read()
            if not blob:
                continue

            sha = hashlib.sha256(blob).hexdigest()
            file_id = f"f_{int(time.time())}_{sha[:16]}"
            saved_name = f"{file_id}{ext}"
            save_path = os.path.join(AI_UPLOADS_DIR, saved_name)

            # if same content already exists, don't rewrite
            if not os.path.exists(save_path):
                with open(save_path, "wb") as f:
                    f.write(blob)

            mimetype = fs.mimetype or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

            meta = {
                "id": file_id,
                "saved_name": saved_name,
                "original_name": original_name,
                "filename": original_name,  # For consistency with chat endpoint
                "path": save_path,  # Needed for AI chat to read file
                "size": len(blob),
                "mimetype": mimetype,
                "sha256": sha,
                "wallet": wallet,
                "guest_id": guest_id,  # ADDED - for ownership tracking when no wallet
                "session_id": session_id,
                "purpose": purpose,
                "created_at": int(time.time()),
            }
            meta_path = os.path.join(AI_UPLOADS_DIR, f"{file_id}.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # Update the unified upload index so chat endpoint can find this file
            idx = load_upload_index()
            idx[file_id] = meta
            save_upload_index(idx)

            uploaded.append({
                "id": file_id,
                "name": original_name,
                "size": len(blob),
                "mimetype": mimetype,
                "sha256": sha
            })

        if not uploaded:
            return jsonify(ok=False, error="No valid files received."), 400

        # Optionally link uploads to a session's memory (so the model can use them later)
        # We store only metadata references, not the raw bytes in the session json.
        if session_id:
            try:
                attach_uploaded_files_to_session(session_id=session_id, wallet=wallet, files=uploaded)
            except Exception as e:
                # don't fail upload if session linking fails
                app.logger.exception("attach_uploaded_files_to_session failed: %s", e)

        # PRIORITY 1: Telemetry - append to index.jsonl for PYTHEIA/IoT knowledge accounting
        try:
            telemetry_index = os.path.join(DATA_DIR, "ai_files", "index.jsonl")
            os.makedirs(os.path.dirname(telemetry_index), exist_ok=True)

            telemetry_entry = {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "event": "file_upload_success",
                "wallet": wallet or guest_id,
                "session_id": session_id,
                "file_count": len(uploaded),
                "total_size": sum(f["size"] for f in uploaded),
                "files": [{"id": f["id"], "name": f["name"], "size": f["size"], "mimetype": f["mimetype"]} for f in uploaded]
            }

            with open(telemetry_index, "a", encoding="utf-8") as f:
                f.write(json.dumps(telemetry_entry, ensure_ascii=False) + "\n")

            app.logger.debug(f"Telemetry recorded: {len(uploaded)} files uploaded")
        except Exception as telemetry_err:
            # Don't fail the upload if telemetry fails
            app.logger.warning(f"Telemetry append failed: {telemetry_err}")

        return jsonify(ok=True, files=uploaded)
    except Exception as e:
        app.logger.exception("Upload failed: %s", e)
        # FIX 1B: Never return 500, use degraded mode pattern
        return jsonify(
            ok=False,
            mode="degraded",
            error="File upload temporarily unavailable",
            error_code="UPLOAD_FAILURE",
            details=str(e),
            fallback_hint="Try again with a smaller file or contact support"
        ), 200


@app.route("/api/ai/files/<file_id>", methods=["GET"])
def api_ai_files_get(file_id):
    """
    Retrieve a previously uploaded file by its file_id.  We look up
    the metadata in the unified AI upload index (AI_UPLOADS_INDEX),
    then stream the file from disk.  If the meta entry or file is
    missing, return 404.  Any other error yields a 500 and logs an
    exception.  Ownership checks are intentionally omitted to allow
    public access to attachments referenced in AI chat responses.
    """
    try:
        idx = load_upload_index()
        meta = idx.get(file_id)
        if not meta:
            return jsonify({"ok": False, "error": "file not found"}), 404

        file_path = meta.get("path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"ok": False, "error": "file missing on disk"}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=meta.get("filename") or os.path.basename(file_path),
            mimetype=meta.get("content_type") or "application/octet-stream",
            conditional=True,
        )
    except Exception as e:
        app.logger.exception("file get failed")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/ai_history", methods=["GET"])
def api_ai_history():
    """
    Ιστορικό AI συνομιλιών για συγκεκριμένο THR wallet.
    Βασίζεται στο ai_offline_corpus.json.
    """
    wallet = (request.args.get("wallet") or "").strip()
    corpus = load_json(AI_CORPUS_FILE, [])

    history = []
    for entry in corpus:
        if wallet and entry.get("wallet") != wallet:
            continue
        ts = entry.get("timestamp", "")
        prompt = entry.get("prompt", "")
        response = entry.get("response", "")

        if prompt:
            history.append({"role": "user", "content": prompt, "ts": ts})
        if response:
            history.append({"role": "assistant", "content": response, "ts": ts})

    history = history[-40:]  # τα τελευταία 40 μηνύματα για να μην φορτώνει άπειρα
    return jsonify({"wallet": wallet, "history": history}), 200

# OLD VERSION - Replaced by api_ai_sessions_combined() which supports both GET/POST and guest mode
# @app.route("/api/ai/sessions", methods=["GET"])
# @app.route("/api/ai_sessions", methods=["GET"])  # backward compat
# def api_ai_sessions():
#
#     wallet = (request.args.get("wallet") or "").strip()
#     if not wallet:
#         return jsonify({"ok": True, "sessions": []})
#
#     try:
#         sessions = load_ai_sessions()
#         sessions = [s for s in sessions if s.get("wallet") == wallet and not s.get("archived")]
#         # newest first
#         def _key(s):
#             return s.get("updated_at") or s.get("created_at") or ""
#         sessions.sort(key=_key, reverse=True)
#         return jsonify({"ok": True, "wallet": wallet, "sessions": sessions})
#     except Exception as e:
#         app.logger.exception("ai_sessions list failed")
#         return jsonify({"ok": False, "error": str(e), "sessions": []}), 500
#
#     # ταξινόμηση με βάση updated_at (πιο πρόσφατη πρώτη)
#     def _key(s):
#         return s.get("updated_at", "")
#     sessions.sort(key=_key, reverse=True)
#
#     return jsonify({"wallet": wallet, "sessions": sessions}), 200

@app.route("/api/ai_sessions/rename", methods=["POST"])
@app.route("/api/ai/sessions/rename", methods=["POST"])  # Add slash version!
def api_ai_session_rename():

    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet") or "").strip()
    session_id = (data.get("session_id") or data.get("id") or "").strip()
    title = (data.get("title") or "").strip()

    if not wallet or not session_id or not title:
        return jsonify({"ok": False, "error": "wallet, session_id, title required"}), 400

    sessions = load_ai_sessions()
    for s in sessions:
        if s.get("id")==session_id and s.get("wallet")==wallet:
            s["title"]=title
            s["updated_at"]=datetime.utcnow().isoformat(timespec="seconds")+"Z"
            save_ai_sessions(sessions)
            return jsonify({"ok": True, "session": s})
    return jsonify({"ok": False, "error": "session not found"}), 404

    mode = (data.get("mode") or "delete").strip().lower()
    # mode: "archive" keeps messages for training but hides from UI.
    new_title = (data.get("title") or "").strip()

    if not wallet or not session_id or not new_title:
        return jsonify(error="Missing parameters"), 400

    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("wallet") == wallet and s.get("id") == session_id:
            s["title"] = new_title[:80]
            found = True
            break
    
    if found:
        save_ai_sessions(sessions)
        return jsonify(status="ok", title=new_title), 200
    else:
        return jsonify(error="Session not found"), 404

# -----------------------------------------------------------------------------
# AI Session Deletion
#
# Provides an endpoint to permanently delete a session and its associated
# history for a given wallet.  Accepts JSON payload with "wallet" and
# "session_id" fields.  If the session exists, it is removed from
# ``ai_sessions.json``, the corresponding entries are removed from the
# ``ai_offline_corpus.json``, and any free usage counters keyed by the
# session identifier are cleared.
#
# The endpoint responds with {"status":"ok"} on success.  If the
# session cannot be found, it returns a 404 with an error message.
# -----------------------------------------------------------------------------
# Legacy route with underscore - kept for backward compatibility
@app.route("/api/ai_sessions/delete", methods=["POST"])
def api_ai_session_delete_legacy():

    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet") or request.args.get("wallet") or "").strip()
    session_id = (data.get("session_id") or data.get("id") or request.args.get("session_id") or "").strip()
    if not wallet or not session_id:
        return jsonify({"ok": False, "error": "wallet and session_id required"}), 400

    try:
        sessions = load_ai_sessions()
        changed = False
        for s in sessions:
            if s.get("id") == session_id and s.get("wallet") == wallet:
                # soft-delete: keep for training, hide from UI
                s["archived"] = True
                s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                changed = True
                break
        if changed:
            save_ai_sessions(sessions)
            return jsonify({"ok": True, "archived": True, "session_id": session_id})
        return jsonify({"ok": False, "error": "session not found"}), 404
    except Exception as e:
        app.logger.exception("ai_session delete failed")
        return jsonify({"ok": False, "error": str(e)}), 500

    if not wallet or not session_id:
        return jsonify(error="Missing parameters"), 400

    sessions = load_ai_sessions()

    # Find target session
    target = None
    for s in sessions:
        if (s.get("wallet") == wallet) and (s.get("id") == session_id):
            target = s
            break

    if not target:
        return jsonify(error="Session not found"), 404

    if mode == "archive":
        # Soft delete: keep data for training but hide from UI
        target["deleted"] = True
        save_ai_sessions(sessions)
        return jsonify(ok=True, mode="archive")

    # Hard delete: remove from sessions + corpus
    sessions = [s for s in sessions if not (s.get("wallet") == wallet and s.get("id") == session_id)]
    save_ai_sessions(sessions)

    # Remove entries from offline corpus for this session
    try:
        corpus = load_json(AI_CORPUS_FILE, [])
        new_corpus = [
            entry
            for entry in corpus
            if not (
                (entry.get("wallet") or "").strip() == wallet
                and (entry.get("session_id") or "").strip() == session_id
            )
        ]
        if len(new_corpus) != len(corpus):
            save_json(AI_CORPUS_FILE, new_corpus)
    except Exception as e:
        print("Corpus delete error", e)

    return jsonify(ok=True, mode="delete")

@app.route("/api/ai_session_history", methods=["GET"])
def api_ai_session_history():
    """
    Ιστορικό για συγκεκριμένη session (wallet + session_id).
    """
    wallet = (request.args.get("wallet") or "").strip()
    session_id = (request.args.get("session_id") or "").strip() or "default"

    # Optional query parameters to control returned history length.  If ``all``
    # is truthy (1/true/yes/all), then the entire history is returned.
    # Otherwise ``limit`` specifies how many messages from the end to return.
    # If limit is not provided or invalid, a default of 50 messages is used.
    # This allows clients to request the full conversation or a bounded number
    # of past messages without modifying the stored corpus.
    limit_param = request.args.get("limit")
    all_flag = str(request.args.get("all", "")).lower() in ("1", "true", "yes", "all")

    corpus = load_json(AI_CORPUS_FILE, [])
    history: list[dict] = []

    for entry in corpus:
        # Filter by wallet when provided
        if wallet and entry.get("wallet") != wallet:
            continue
        if (entry.get("session_id") or "default") != session_id:
            continue

        ts = entry.get("timestamp", "")
        prompt = entry.get("prompt", "")
        response = entry.get("response", "")

        if prompt:
            history.append({"role": "user", "content": prompt, "ts": ts})
        if response:
            history.append({"role": "assistant", "content": response, "ts": ts})

    # Apply limit unless the caller explicitly requests the full conversation
    if not all_flag:
        try:
            # If limit is provided use it, otherwise default to 50
            limit = int(limit_param) if limit_param else 50
        except (TypeError, ValueError):
            limit = 50
        # Only slice history if limit is positive
        if limit > 0:
            history = history[-limit:]

    return jsonify({"wallet": wallet, "session_id": session_id, "history": history}), 200


@app.route("/api/ai_packs", methods=["GET"])
def api_ai_packs():
    """
    Επιστρέφει τη λίστα των διαθέσιμων AI packs.
    Αν υπάρχει ai_packs.json στο DATA_DIR, το διαβάζει από εκεί,
    αλλιώς χρησιμοποιεί τα AI_DEFAULT_PACKS.
    """
    packs = load_ai_packs()
    return jsonify({"packs": packs}), 200


@app.route("/api/ai_purchase_pack", methods=["POST"])
def api_ai_purchase_pack():
    """
    Πληρωμή AI pack με THR:

    - Παίρνει { wallet, pack } από JSON
    - Ελέγχει υπόλοιπο στο ledger
    - Χρεώνει τον χρήστη, πιστώνει το AI_WALLET_ADDRESS
    - Γράφει service_payment TX στο CHAIN_FILE
    - Αυξάνει τα credits του wallet στο ai_credits.json
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or "").strip()
    code   = (data.get("pack") or "").strip()

    if not wallet or not code:
        return jsonify(
            status="denied",
            message="Wallet και pack code είναι υποχρεωτικά."
        ), 400

    packs = load_ai_packs()
    pack = next((p for p in packs if p.get("code") == code), None)
    if not pack:
        return jsonify(status="denied", message="Άγνωστο AI pack."), 400

    try:
        price = float(pack.get("price_thr", 0.0))
    except Exception:
        price = 0.0

    if price <= 0:
        return jsonify(status="denied", message="Μη έγκυρη τιμή πακέτου."), 400

    # --- Ledger έλεγχος & μεταφορά THR ---
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(wallet, 0.0))

    if balance < price:
        return jsonify(
            status="denied",
            message=f"Insufficient THR funds (έχεις {balance}, χρειάζονται {price})."
        ), 400

    ledger[wallet] = round(balance - price, 6)
    ledger[AI_WALLET_ADDRESS] = round(
        float(ledger.get(AI_WALLET_ADDRESS, 0.0)) + price,
        6,
    )
    save_json(LEDGER_FILE, ledger)

    # --- Credits ledger ---
    credits = load_ai_credits()
    current_credits = int(credits.get(wallet, 0))
    add_credits = int(pack.get("credits", 0))
    total_credits = current_credits + add_credits
    credits[wallet] = total_credits
    save_ai_credits(credits)

    # --- Chain TX (service_payment) ---
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "service_payment",
        "service": "AI_PACK",
        "pack_code": pack.get("code"),
        "pack_credits": add_credits,
        "from": wallet,
        "to": AI_WALLET_ADDRESS,
        "amount": price,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"AI-{int(time.time())}-{len(chain)}",
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)

    print(
        f"🤖 AI Pack purchased: {pack.get('code')} by {wallet} "
        f"({add_credits} credits, total={total_credits})"
    )

    return jsonify(
        status="granted",
        pack=pack,
        total_credits=total_credits,
    ), 200


# ─── NODE REGISTRATION / IOT KIT ───────────────────
@app.route("/register_node", methods=["POST"])
def register_node():
    address = request.form.get("address","").strip()
    secret  = request.form.get("secret","").strip()
    if not address or not secret:
        return "Address and Secret are required",400
    node_id=str(uuid.uuid4())
    config={
        "node_id":node_id,
        "wallet_address":address,
        "secret":secret,
        "server_url":"https://thrchain.up.railway.app"
    }
    config_json=json.dumps(config,indent=4)
    start_script=f"""
import os, sys, subprocess
print("Starting Thronos IoT Vehicle Node...")
print("Node ID: {node_id}")
print("Wallet: {address}")
try:
    import PIL, requests, cryptography  # noqa
except Exception:
    print("Installing dependencies (pillow, requests, cryptography)...")
    subprocess.check_call([sys.executable,"-m","pip","install","requests","pillow","cryptography"])
try:
    subprocess.run([sys.executable,"iot_vehicle_node.py"], check=True)
except KeyboardInterrupt:
    print("\\nNode stopped.")
except Exception as e:
    print(f"Error: {{e}}"); input("Press Enter to exit...")
"""
    try:
        with open(os.path.join(BASE_DIR,"iot_vehicle_node.py"),"r",encoding="utf-8") as f:
            node_script=f.read()
    except FileNotFoundError:
        node_script="# iot_vehicle_node.py not found on server."
    memory_file=io.BytesIO()
    with zipfile.ZipFile(memory_file,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("node_config.json",config_json)
        zf.writestr("start_iot.py",start_script)
        zf.writestr("iot_vehicle_node.py",node_script)
        pic_path=os.path.join(BASE_DIR,"images/Vehicle.jpg") # FIX: Remove leading slash
        if os.path.exists(pic_path):
            zf.write(pic_path,"images/Vehicle.jpg")
        else:
            zf.writestr("images/Vehicle.jpg","")
        zf.writestr("README.txt","1. Install Python 3.\\n2. Run 'python start_iot.py' (auto-installs deps).")
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"iot_node_kit_{node_id[:8]}.zip"
    )


# ─── PLEDGE FLOW ───────────────────────────────────
@app.route("/pledge")
def pledge_form():
    return render_template("pledge_form.html")

@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data = request.get_json() or {}
    btc_address=(data.get("btc_address") or "").strip()
    pledge_text=(data.get("pledge_text") or "").strip()
    passphrase=(data.get("passphrase") or "").strip()
    if not btc_address:
        return jsonify(error="Missing BTC address"),400
    pledges = load_json(PLEDGE_CHAIN, [])
    exists = next((p for p in pledges if p["btc_address"]==btc_address), None)
    if exists:
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=exists.get("pdf_filename",f"pledge_{exists['thr_address']}.pdf")
        ),200
    free_list=load_json(WHITELIST_FILE,[])
    paid, txns = (True,[]) if btc_address in free_list else verify_btc_payment(btc_address)
    if not paid:
        return jsonify(status="pending",message="Waiting for BTC payment",txns=txns),200

    # Generate proper THR address (THR + 40 hex chars)
    timestamp = str(int(time.time() * 1000))
    thr_addr = generate_thr_address(btc_address, timestamp)
    phash = hashlib.sha256((btc_address+pledge_text).encode()).hexdigest()
    send_seed=secrets.token_hex(16)
    send_seed_hash=hashlib.sha256(send_seed.encode()).hexdigest()
    auth_string=f"{send_seed}:{passphrase}:auth" if passphrase else f"{send_seed}:auth"
    send_auth_hash=hashlib.sha256(auth_string.encode()).hexdigest()
    pledge_entry={
        "btc_address":btc_address,
        "pledge_text":pledge_text,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash":phash,
        "thr_address":thr_addr,
        "send_seed_hash":send_seed_hash,
        "send_auth_hash":send_auth_hash,
        "has_passphrase":bool(passphrase)
    }
    chain=load_json(CHAIN_FILE,[])
    height=len(chain)
    pdf_name=create_secure_pdf_contract(
        btc_address, pledge_text, thr_addr, phash, height, send_seed, CONTRACTS_DIR, passphrase
    )
    pledge_entry["pdf_filename"]=pdf_name
    pledges.append(pledge_entry)
    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(
        status="verified",
        thr_address=thr_addr,
        pledge_hash=phash,
        pdf_filename=pdf_name,
        send_secret=send_seed
    ),200


@app.route("/wallet_data/<thr_addr>")
def wallet_data(thr_addr):
    balances = get_wallet_balances(thr_addr)
    chain = load_chain_cached()
    history = [
        tx for tx in chain
        if isinstance(tx, dict) and (tx.get("from") == thr_addr or tx.get("to") == thr_addr)
    ]
    return jsonify(
        balance=balances["thr"],
        wbtc_balance=balances["wbtc"],
        l2e_balance=balances["l2e"],
        transactions=history,
    ), 200

def get_token_price_in_thr(symbol):
    """
    Calculate token price in THR from liquidity pool reserves.
    Returns price as THR per 1 unit of token, or 1.0 if no pool exists.
    """
    if symbol == "THR":
        return 1.0

    pools = load_pools()

    # Find pool with THR and the token
    for pool in pools:
        token_a = pool.get("token_a", "")
        token_b = pool.get("token_b", "")
        reserves_a = float(pool.get("reserves_a", 0))
        reserves_b = float(pool.get("reserves_b", 0))

        if reserves_a <= 0 or reserves_b <= 0:
            continue

        # Pool is THR/TOKEN
        if token_a == "THR" and token_b == symbol:
            # Price of TOKEN in THR = reserves_a / reserves_b
            return reserves_a / reserves_b

        # Pool is TOKEN/THR
        if token_a == symbol and token_b == "THR":
            # Price of TOKEN in THR = reserves_b / reserves_a
            return reserves_b / reserves_a

    # No pool found, return 1.0 as fallback
    return 1.0

@app.route("/api/wallet/tokens/<thr_addr>")
def api_wallet_tokens(thr_addr):
    """
    Returns all token balances for a wallet with metadata (logos, names, etc.)
    Perfect for wallet widgets and balance displays
    """
    balances = get_wallet_balances(thr_addr)
    tokens = balances["tokens"]

    show_zero = request.args.get("show_zero", "true").lower() == "true"
    if not show_zero:
        tokens = [t for t in tokens if t.get("balance", 0) > 0]

    total_value_usd = 0  # Placeholder for future price oracle integration

    return jsonify({
        "address": thr_addr,
        "tokens": tokens,
        "total_tokens": len(tokens),
        "total_value_usd": total_value_usd,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }), 200


@app.route("/api/balance/<thr_addr>", methods=["GET"])
def api_balance_alias(thr_addr: str):
    """Compatibility alias that exposes a consolidated balance snapshot."""
    balances = get_wallet_balances(thr_addr)

    mempool_pending = [
        tx for tx in load_mempool()
        if isinstance(tx, dict) and (tx.get("from") == thr_addr or tx.get("to") == thr_addr or tx.get("thr_address") == thr_addr)
    ]

    return jsonify({
        "address": thr_addr,
        "thr_balance": balances["thr"],
        "token_balances": balances["token_balances"],
        "mempool_pending": mempool_pending,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }), 200

@app.route("/wallet/<thr_addr>")
def wallet_redirect(thr_addr):
    return redirect(url_for("wallet_data", thr_addr=thr_addr)),302

@app.route("/widget/wallet")
def wallet_widget():
    """
    Embeddable wallet widget showing all token balances with logos

    URL Parameters:
    - address: THR wallet address (required or uses default)
    - compact: true/false - compact mode for smaller displays
    - show_zero: true/false - show tokens with zero balance
    - refresh: auto-refresh interval in seconds (0 = disabled)

    Example: /widget/wallet?address=THR123...&compact=true&refresh=30
    """
    return render_template("wallet_widget.html")


# ─── EXPERIMENTAL TOKENS SYSTEM ─────────────────────────────────────────────

CUSTOM_TOKENS_FILE = os.path.join(DATA_DIR, "custom_tokens.json")
CUSTOM_TOKENS_LEDGER_DIR = os.path.join(DATA_DIR, "custom_ledgers")

os.makedirs(CUSTOM_TOKENS_LEDGER_DIR, exist_ok=True)

# CRITICAL FIX #2: Ensure tokens logo directory exists
STATIC_TOKENS_DIR = os.path.join(BASE_DIR, "static", "img", "tokens")
os.makedirs(STATIC_TOKENS_DIR, exist_ok=True)

def load_custom_tokens():
    """Load custom tokens registry"""
    return load_json(CUSTOM_TOKENS_FILE, {})

def save_custom_tokens(tokens):
    """Save custom tokens registry"""
    save_json(CUSTOM_TOKENS_FILE, tokens)

def resolve_token_logo(token_data: dict) -> str:
    """
    CRITICAL FIX #2: Resolve token logo with canonical path mapping.
    Returns relative path - caller adds /media/ or /static/ prefix.

    Fallback order:
    1. token_data['logo_path'] (custom tokens in DATA_DIR/media/token_logos)
    2. DATA_DIR/media/token_logos/<SYMBOL>_*.* (uploaded custom logos)
    3. /static/img/tokens/<SYMBOL>.png (built-in tokens)
    4. /static/img/<SYMBOL>.png (legacy built-in)
    5. None (frontend shows circle letter icon)
    """
    # Check if logo_path already exists (custom tokens)
    # This will be something like "token_logos/SYMBOL_timestamp.ext"
    if token_data.get("logo_path"):
        return token_data["logo_path"]

    symbol = token_data.get("symbol", "").upper()

    # Strategy 1: Check DATA_DIR/media/token_logos/ (uploaded custom tokens)
    if symbol:
        token_logos_dir = os.path.join(DATA_DIR, "media", "token_logos")
        if os.path.exists(token_logos_dir):
            # Look for files matching SYMBOL_* pattern
            for filename in os.listdir(token_logos_dir):
                if filename.startswith(f"{symbol}_"):
                    return f"token_logos/{filename}"

    # Strategy 2: Check /static/img/tokens/ (built-in tokens)
    if symbol:
        static_tokens_dir = os.path.join(BASE_DIR, "static", "img", "tokens")

        # Try SYMBOL.png
        png_path = os.path.join(static_tokens_dir, f"{symbol}.png")
        if os.path.exists(png_path):
            return f"img/tokens/{symbol}.png"

        # Try lowercase variant
        png_lower = os.path.join(static_tokens_dir, f"{symbol.lower()}.png")
        if os.path.exists(png_lower):
            return f"img/tokens/{symbol.lower()}.png"

    # Strategy 3: Check /static/img/ (legacy built-in)
    if symbol:
        static_img_dir = os.path.join(BASE_DIR, "static", "img")

        # Try legacy .png
        legacy_png = os.path.join(static_img_dir, f"{symbol}.png")
        if os.path.exists(legacy_png):
            return f"img/{symbol}.png"

        # Try legacy .webp
        legacy_webp = os.path.join(static_img_dir, f"{symbol}.webp")
        if os.path.exists(legacy_webp):
            return f"img/{symbol}.webp"

    return None

def get_custom_token_entry_by_symbol(symbol: str):
    symbol = (symbol or "").upper()
    tokens = load_custom_tokens()
    return tokens.get(symbol)

def load_custom_token_ledger(token_id):
    """Load ledger for a specific custom token"""
    ledger_file = os.path.join(CUSTOM_TOKENS_LEDGER_DIR, f"{token_id}.json")
    return load_json(ledger_file, {})

def save_custom_token_ledger(token_id, ledger):
    """Save ledger for a specific custom token"""
    ledger_file = os.path.join(CUSTOM_TOKENS_LEDGER_DIR, f"{token_id}.json")
    save_json(ledger_file, ledger)

def load_custom_token_ledger_by_symbol(symbol: str):
    token_entry = get_custom_token_entry_by_symbol(symbol)
    if not token_entry:
        return None
    return load_custom_token_ledger(token_entry.get("id"))

def save_custom_token_ledger_by_symbol(symbol: str, ledger):
    token_entry = get_custom_token_entry_by_symbol(symbol)
    if not token_entry:
        return
    save_custom_token_ledger(token_entry.get("id"), ledger)

@app.route("/api/tokens/create", methods=["POST"])
def api_create_token():
    """Create a custom experimental token with optional logo upload"""
    # Support both JSON and form-data (for file upload)
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = request.form.to_dict()

    creator = (data.get("creator_address") or "").strip()
    symbol = (data.get("symbol") or "").strip().upper()
    name = (data.get("name") or "").strip()
    decimals = int(data.get("decimals", 6))
    initial_supply = float(data.get("initial_supply", 0))
    max_supply = float(data.get("max_supply", 0))
    color = (data.get("color") or "#00ff66").strip()
    description = (data.get("description") or "").strip()

    # Token permissions (creator-controlled)
    # Handle both JSON booleans and FormData strings ("true"/"false")
    def parse_bool(val, default=False):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes', 'on')
        return default

    transferable = parse_bool(data.get("transferable"), True)  # Default: tokens can be sent
    burnable = parse_bool(data.get("burnable"), False)  # Default: tokens cannot be burned
    mintable = parse_bool(data.get("mintable"), False)  # Default: cannot mint new tokens

    # Check for logo file upload (optional, FREE!)
    logo_file = request.files.get("logo") if request.files else None

    if not creator or not validate_thr_address(creator):
        return jsonify({"ok": False, "error": "Invalid creator address"}), 400
    if not symbol or len(symbol) < 3 or len(symbol) > 10:
        return jsonify({"ok": False, "error": "Symbol must be 3-10 characters"}), 400
    if not name or len(name) < 3:
        return jsonify({"ok": False, "error": "Name must be at least 3 characters"}), 400
    if decimals < 0 or decimals > 18:
        return jsonify({"ok": False, "error": "Decimals must be between 0 and 18"}), 400
    if initial_supply < 0:
        return jsonify({"ok": False, "error": "Initial supply cannot be negative"}), 400
    if max_supply > 0 and initial_supply > max_supply:
        return jsonify({"ok": False, "error": "Initial supply cannot exceed max supply"}), 400

    tokens = load_custom_tokens()
    if symbol in tokens:
        return jsonify({"ok": False, "error": f"Token {symbol} already exists"}), 400

    # --- DEDUCT 100 THR FEE FROM CREATOR ---
    CREATION_FEE = 100.0
    ledger = load_json(LEDGER_FILE, {})
    creator_balance = float(ledger.get(creator, 0.0))

    if creator_balance < CREATION_FEE:
        return jsonify({
            "ok": False,
            "error": f"Insufficient balance. You need {CREATION_FEE} THR to create a token.",
            "balance": round(creator_balance, 6),
            "required": CREATION_FEE
        }), 400

    # Deduct fee from creator
    ledger[creator] = round(creator_balance - CREATION_FEE, 6)

    # Add fee to AI wallet
    ai_balance = float(ledger.get(AI_WALLET_ADDRESS, 0.0))
    ledger[AI_WALLET_ADDRESS] = round(ai_balance + CREATION_FEE, 6)

    save_json(LEDGER_FILE, ledger)

    # Record the fee transaction in the chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    fee_tx_id = f"TOKEN_FEE-{int(time.time())}-{secrets.token_hex(4)}"
    fee_tx = {
        "type": "token_creation_fee",
        "from": creator,
        "to": AI_WALLET_ADDRESS,
        "amount": CREATION_FEE,
        "token_symbol": symbol,
        "timestamp": ts,
        "tx_id": fee_tx_id,
        "status": "confirmed"
    }
    chain.append(fee_tx)
    save_json(CHAIN_FILE, chain)

    # Create the token
    token_id = f"TOKEN_{secrets.token_hex(8)}"
    token = {
        "id": token_id,
        "symbol": symbol,
        "name": name,
        "decimals": decimals,
        "initial_supply": initial_supply,
        "max_supply": max_supply,
        "current_supply": initial_supply,
        "creator": creator,
        "logo": None,
        "color": color,
        "description": description,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "type": "experimental",
        "chain": "Thronos",
        "creation_fee_paid": CREATION_FEE,
        "creation_fee_tx": fee_tx_id,
        # Token permissions
        "transferable": transferable,
        "burnable": burnable,
        "mintable": mintable
    }

    tokens[symbol] = token
    save_custom_tokens(tokens)

    # Handle logo upload if provided (FREE - no extra charge!)
    if logo_file and logo_file.filename:
        try:
            ext = os.path.splitext(secure_filename(logo_file.filename))[1] or ".png"
            # Collision-free naming: SYMBOL_timestamp.ext
            timestamp = int(time.time() * 1000)
            logo_filename = f"{symbol}_{timestamp}{ext}"
            logo_path = os.path.join(TOKEN_LOGOS_DIR, logo_filename)

            logger.info(f"Saving logo for {symbol} to: {logo_path}")
            logo_file.save(logo_path)

            # Verify file was saved
            if os.path.exists(logo_path):
                token["logo_path"] = f"token_logos/{logo_filename}"
                tokens[symbol] = token
                save_custom_tokens(tokens)
                logger.info(f"Logo saved successfully for token {symbol}: {token['logo_path']}")
            else:
                logger.warning(f"Logo file not found after save for token {symbol}")
        except Exception as e:
            logger.error(f"Failed to save logo for token {symbol}: {e}", exc_info=True)

    if initial_supply > 0:
        token_ledger = {creator: initial_supply}
        save_custom_token_ledger(token_id, token_ledger)

    if token.get("logo_path"):
        token["logo"] = f"/media/{token['logo_path']}"

    logger.info(f"Created experimental token {symbol} by {creator} (fee: {CREATION_FEE} THR)")
    return jsonify({
        "ok": True,
        "token": token,
        "creator_new_balance": ledger[creator],
        "fee_paid": CREATION_FEE,
        "fee_tx_id": fee_tx_id
    }), 200

@app.route("/api/tokens/upload_logo/<symbol>", methods=["POST"])
def api_upload_token_logo(symbol):
    """Upload logo for a custom token"""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    file = request.files["file"]
    creator = request.form.get("creator_address", "").strip()

    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    tokens = load_custom_tokens()
    token = tokens.get(symbol.upper())

    if not token:
        return jsonify({"ok": False, "error": "Token not found"}), 404

    if token["creator"] != creator:
        logger.warning(f"Logo upload unauthorized for {symbol}: {creator} != {token['creator']}")
        return jsonify({"ok": False, "error": "Not authorized"}), 403

    try:
        # Save logo with collision-free naming: SYMBOL_timestamp.ext
        ext = os.path.splitext(secure_filename(file.filename))[1] or ".png"
        timestamp = int(time.time() * 1000)
        logo_filename = f"{symbol}_{timestamp}{ext}"
        logo_path = os.path.join(TOKEN_LOGOS_DIR, logo_filename)

        logger.info(f"Uploading logo for {symbol} to: {logo_path}")
        file.save(logo_path)

        if not os.path.exists(logo_path):
            return jsonify({"ok": False, "error": "Failed to save logo file"}), 500
    except Exception as e:
        logger.error(f"Error saving logo for {symbol}: {e}", exc_info=True)
        return jsonify({"ok": False, "error": f"Failed to save logo: {str(e)}"}), 500

    # Update token
    token["logo_path"] = f"token_logos/{logo_filename}"
    tokens[symbol.upper()] = token
    save_custom_tokens(tokens)

    logo_url = f"/media/{token['logo_path']}"
    token["logo"] = logo_url

    logger.info(f"Logo uploaded successfully for {symbol}: {token['logo_path']}")
    return jsonify({"ok": True, "logo_path": token["logo_path"], "logo": logo_url}), 200

@app.route("/api/tokens/list")
def api_list_tokens():
    """
    List all custom tokens.
    PRIORITY 3: Applies logo fallback resolution to all tokens.
    """
    tokens = load_custom_tokens()
    token_list = list(tokens.values())

    # PRIORITY 3: Resolve logos for all tokens
    for token in token_list:
        logo = resolve_token_logo(token)
        if logo:
            token["logo_path"] = logo
            token["logo_url"] = f"/static/{logo}"

    token_list.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return jsonify({"ok": True, "tokens": token_list}), 200

@app.route("/api/tokens/<symbol>/balance/<address>")
def api_token_balance(symbol, address):
    """Get balance for a specific custom token"""
    tokens = load_custom_tokens()
    token = tokens.get(symbol.upper())
    if not token:
        return jsonify({"ok": False, "error": "Token not found"}), 404
    ledger = load_custom_token_ledger(token["id"])
    balance = float(ledger.get(address, 0))
    return jsonify({"ok": True, "symbol": symbol.upper(), "address": address, "balance": balance, "token": token}), 200


@app.route("/api/tokens/transfer", methods=["POST"])
def api_token_transfer():
    """Back-compat token transfer endpoint used by older frontends.

    Routes to the unified transfer_custom_token function which handles:
    - Both token stores (TOKENS_FILE and CUSTOM_TOKENS_FILE)
    - Fee payment in THR
    - Speed options (slow/fast)
    """
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    # Accept both naming conventions
    symbol = data.get("symbol") or data.get("token") or data.get("ticker")
    amount = data.get("amount")

    from_addr = data.get("from") or data.get("from_thr") or data.get("from_address")
    to_addr = data.get("to") or data.get("to_thr") or data.get("to_address")

    missing = []
    if not from_addr:
        missing.append("from")
    if not to_addr:
        missing.append("to")
    if not symbol:
        missing.append("symbol")
    if amount is None:
        missing.append("amount")

    if missing:
        return jsonify({"ok": False, "error": f"Missing required fields: {', '.join(missing)}"}), 400

    from_thr = str(from_addr).strip()
    to_thr = str(to_addr).strip()
    symbol = str(symbol).strip().upper()
    auth_secret = str(data.get("auth_secret", "")).strip()
    passphrase = str(data.get("passphrase", "")).strip() if data.get("passphrase") else ""
    speed = str(data.get("speed", "fast")).strip().lower()

    try:
        amount = float(amount)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"ok": False, "error": "Amount must be > 0"}), 400

    if not validate_thr_address(from_thr) or not validate_thr_address(to_thr):
        return jsonify({"ok": False, "error": "Invalid address format"}), 400

    # First try custom_tokens.json (dict-based, newer format)
    custom_tokens = load_custom_tokens()
    if symbol in custom_tokens:
        return transfer_custom_token(symbol, from_thr, to_thr, amount, auth_secret, passphrase, speed)

    # Fallback to tokens.json (list-based, older format)
    tokens = load_json(TOKENS_FILE, [])
    token = next((t for t in tokens if str(t.get("symbol", "")).upper() == symbol), None)
    if not token:
        return jsonify({"ok": False, "error": f"Token {symbol} not found"}), 404

    # Check if token is transferable
    if not token.get("transferable", True):
        return jsonify({"ok": False, "error": "This token is not transferable"}), 403

    # Auth: same logic as /api/wallet/send for custom tokens
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify({"ok": False, "error": "Sender address not found"}), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify({"ok": False, "error": "Send not enabled for this address"}), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify({"ok": False, "error": "Passphrase required"}), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"ok": False, "error": "Invalid authentication"}), 403

    # Ledger update
    token_id = token.get("id") or token.get("token_id") or symbol
    decimals = int(token.get("decimals", 6))

    # Check token balance
    token_ledger = load_custom_token_ledger(token_id)
    sender_token_balance = float(token_ledger.get(from_thr, 0.0))

    if sender_token_balance < amount:
        return jsonify({
            "ok": False,
            "error": f"Insufficient {symbol} balance",
            "balance": round(sender_token_balance, decimals),
            "required": amount
        }), 400

    # Calculate fee in THR
    if speed == "slow":
        thr_fee = round(max(0.001, amount * 0.0009), 6)
    else:
        thr_fee = round(max(0.001, calculate_dynamic_fee(amount)), 6)

    # Check THR balance for fee
    thr_ledger = load_json(LEDGER_FILE, {})
    sender_thr_balance = float(thr_ledger.get(from_thr, 0.0))

    if sender_thr_balance < thr_fee:
        return jsonify({
            "ok": False,
            "error": "Insufficient THR balance for transaction fee",
            "thr_balance": round(sender_thr_balance, 6),
            "fee_required": thr_fee,
            "token_balance": round(sender_token_balance, decimals)
        }), 400

    # Deduct THR fee (burn it)
    thr_ledger[from_thr] = round(sender_thr_balance - thr_fee, 6)
    save_json(LEDGER_FILE, thr_ledger)

    # Transfer the token
    token_ledger[from_thr] = round(sender_token_balance - amount, decimals)
    token_ledger[to_thr] = round(float(token_ledger.get(to_thr, 0.0)) + amount, decimals)
    save_custom_token_ledger(token_id, token_ledger)

    # Chain record (confirmed)
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"TOKEN_TRANSFER-{symbol}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_transfer",
        "token_symbol": symbol,
        "token_id": token_id,
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, decimals),
        "fee_burned_thr": thr_fee,
        "speed": speed,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }

    chain = load_json(CHAIN_FILE, [])
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    logger.info(f"Token transfer: {amount} {symbol} from {from_thr[:10]}... to {to_thr[:10]}... (fee: {thr_fee} THR)")

    return jsonify({
        "ok": True,
        "status": "confirmed",
        "tx": tx,
        "new_balance": token_ledger[from_thr],
        "new_thr_balance": thr_ledger[from_thr],
        "fee_burned": thr_fee
    }), 200

@app.route("/api/tokens/burn", methods=["POST"])
def api_token_burn():
    """
    Burn (destroy) custom tokens, reducing total supply.
    Requires burnable permission to be enabled on the token.
    """
    data = request.get_json() or {}
    symbol = (data.get("symbol") or "").strip().upper()
    from_thr = (data.get("from_thr") or "").strip()
    amount_raw = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if not symbol:
        return jsonify({"ok": False, "error": "Symbol is required"}), 400
    if not from_thr:
        return jsonify({"ok": False, "error": "Address required"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "Amount must be positive"}), 400
    if not auth_secret:
        return jsonify({"ok": False, "error": "Authentication secret required"}), 400

    # Get token and check if it exists
    tokens = load_custom_tokens()
    token = tokens.get(symbol)
    if not token:
        return jsonify({"ok": False, "error": f"Token {symbol} not found"}), 404

    # Check if token is burnable
    if not token.get("burnable", False):
        return jsonify({
            "ok": False,
            "error": "This token is not burnable",
            "reason": "The token creator has not enabled burning for this token"
        }), 403

    # Validate sender's pledge and auth
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify({"ok": False, "error": "Address not found in pledge registry"}), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify({"ok": False, "error": "Send not enabled for this address"}), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify({"ok": False, "error": "Passphrase required"}), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"ok": False, "error": "Invalid authentication"}), 403

    # Update token ledger - burn tokens
    ledger = load_custom_token_ledger(token["id"])
    sender_balance = float(ledger.get(from_thr, 0.0))

    if sender_balance < amount:
        return jsonify({
            "ok": False,
            "error": "Insufficient balance",
            "balance": round(sender_balance, token["decimals"]),
            "required": amount
        }), 400

    ledger[from_thr] = round(sender_balance - amount, token["decimals"])
    save_custom_token_ledger(token["id"], ledger)

    # Update token supply
    token["current_supply"] = round(token["current_supply"] - amount, token["decimals"])
    tokens[symbol] = token
    save_custom_tokens(tokens)

    # Record transaction in chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"TOKEN_BURN-{symbol}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_burn",
        "token_symbol": symbol,
        "token_id": token["id"],
        "from": from_thr,
        "amount": round(amount, token["decimals"]),
        "new_supply": token["current_supply"],
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    logger.info(f"Token burn: {amount} {symbol} burned by {from_thr}, new supply: {token['current_supply']}")
    return jsonify({
        "ok": True,
        "status": "confirmed",
        "tx": tx,
        "new_balance": ledger[from_thr],
        "new_supply": token["current_supply"]
    }), 200

@app.route("/api/tokens/mint", methods=["POST"])
def api_token_mint():
    """
    Mint (create) new custom tokens, increasing total supply.
    Requires mintable permission to be enabled on the token.
    Only the token creator can mint new tokens.
    """
    data = request.get_json() or {}
    symbol = (data.get("symbol") or "").strip().upper()
    creator = (data.get("creator") or "").strip()
    to_thr = (data.get("to_thr") or "").strip()
    amount_raw = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if not symbol:
        return jsonify({"ok": False, "error": "Symbol is required"}), 400
    if not creator or not to_thr:
        return jsonify({"ok": False, "error": "Creator and recipient addresses required"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "Amount must be positive"}), 400
    if not auth_secret:
        return jsonify({"ok": False, "error": "Authentication secret required"}), 400

    # Get token and check if it exists
    tokens = load_custom_tokens()
    token = tokens.get(symbol)
    if not token:
        return jsonify({"ok": False, "error": f"Token {symbol} not found"}), 404

    # Check if requester is the token creator
    if token["creator"] != creator:
        return jsonify({
            "ok": False,
            "error": "Only the token creator can mint new tokens",
            "creator": token["creator"]
        }), 403

    # Check if token is mintable
    if not token.get("mintable", False):
        return jsonify({
            "ok": False,
            "error": "This token is not mintable",
            "reason": "The token creator has not enabled minting for this token"
        }), 403

    # Check max supply constraint
    if token.get("max_supply", 0) > 0:
        new_supply = token["current_supply"] + amount
        if new_supply > token["max_supply"]:
            return jsonify({
                "ok": False,
                "error": "Minting would exceed max supply",
                "current_supply": token["current_supply"],
                "max_supply": token["max_supply"],
                "requested_mint": amount
            }), 400

    # Validate creator's pledge and auth
    pledges = load_json(PLEDGE_CHAIN, [])
    creator_pledge = next((p for p in pledges if p.get("thr_address") == creator), None)
    if not creator_pledge:
        return jsonify({"ok": False, "error": "Creator address not found in pledge registry"}), 404

    stored_auth_hash = creator_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify({"ok": False, "error": "Send not enabled for creator address"}), 400

    if creator_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify({"ok": False, "error": "Passphrase required"}), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"ok": False, "error": "Invalid authentication"}), 403

    # Mint tokens - add to recipient balance
    ledger = load_custom_token_ledger(token["id"])
    ledger[to_thr] = round(float(ledger.get(to_thr, 0.0)) + amount, token["decimals"])
    save_custom_token_ledger(token["id"], ledger)

    # Update token supply
    token["current_supply"] = round(token["current_supply"] + amount, token["decimals"])
    tokens[symbol] = token
    save_custom_tokens(tokens)

    # Record transaction in chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"TOKEN_MINT-{symbol}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_mint",
        "token_symbol": symbol,
        "token_id": token["id"],
        "minted_by": creator,
        "to": to_thr,
        "amount": round(amount, token["decimals"]),
        "new_supply": token["current_supply"],
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    logger.info(f"Token mint: {amount} {symbol} minted by {creator} to {to_thr}, new supply: {token['current_supply']}")
    return jsonify({
        "ok": True,
        "status": "confirmed",
        "tx": tx,
        "new_balance": ledger[to_thr],
        "new_supply": token["current_supply"]
    }), 200


# ─── UNIFIED WALLET SEND ENDPOINT ─────────────────────────────
@app.route("/api/wallet/send", methods=["POST"])
def api_wallet_send():
    """
    Unified send endpoint for wallet extensions (Chrome, Firefox, Brave).
    Routes to the appropriate handler based on token type.
    """
    data = request.get_json() or {}
    token = (data.get("token") or "THR").upper()
    from_addr = (data.get("from") or data.get("from_thr") or "").strip()
    to_addr = (data.get("to") or data.get("to_thr") or "").strip()
    amount = data.get("amount", 0)
    secret = (data.get("secret") or data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    speed = (data.get("speed") or "fast").lower()

    if token == "THR":
        # Native THR send
        from flask import g
        g.internal_call = True
        return send_thr_internal(from_addr, to_addr, amount, secret, passphrase, speed)
    else:
        # Custom token transfer (fee paid in THR)
        return transfer_custom_token(token, from_addr, to_addr, amount, secret, passphrase, speed)


def send_thr_internal(from_thr, to_thr, amount_raw, auth_secret, passphrase="", speed="fast"):
    """Internal THR send function for unified API."""
    if not validate_thr_address(from_thr):
        return jsonify(error="invalid_from_address", message="Invalid THR address format"), 400
    if not validate_thr_address(to_thr):
        return jsonify(error="invalid_to_address", message="Invalid THR address format"), 400

    valid, error_msg = validate_amount(amount_raw)
    if not valid:
        return jsonify(error="invalid_amount", message=error_msg), 400

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid_amount"), 400

    if not auth_secret:
        return jsonify(error="missing_auth_secret"), 400

    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(error="invalid_auth"), 403

    if speed == "slow":
        fee = round(amount * 0.0009, 6)
    else:
        fee = calculate_dynamic_fee(amount)

    total_cost = amount + fee
    ledger = load_json(LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_thr, 0.0))

    if sender_balance < total_cost:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance, 6),
            required=total_cost,
            fee=fee
        ), 400

    ledger[from_thr] = round(sender_balance - total_cost, 6)
    ledger[to_thr] = round(float(ledger.get(to_thr, 0.0)) + amount, 6)
    save_json(LEDGER_FILE, ledger)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx = {
        "type": "transfer",
        "timestamp": ts,
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, 6),
        "fee_burned": fee,
        "speed": speed
    }
    chain = load_json(CHAIN_FILE, [])
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    return jsonify({
        "ok": True,
        "status": "confirmed",
        "tx": tx,
        "new_balance": ledger[from_thr],
        "fee": fee
    }), 200


def transfer_custom_token(symbol, from_thr, to_thr, amount_raw, auth_secret, passphrase="", speed="fast"):
    """Internal custom token transfer for unified API.

    Fee is paid in THR (not the custom token) using the same fee structure as THR transfers.
    This ensures all token transfers contribute to the network economy.
    """
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if not symbol:
        return jsonify({"ok": False, "error": "Symbol is required"}), 400
    if not from_thr or not to_thr:
        return jsonify({"ok": False, "error": "From and to addresses required"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "Amount must be positive"}), 400
    if not auth_secret:
        return jsonify({"ok": False, "error": "Authentication secret required"}), 400

    tokens = load_custom_tokens()
    token = tokens.get(symbol)
    if not token:
        return jsonify({"ok": False, "error": f"Token {symbol} not found"}), 404

    if not token.get("transferable", True):
        return jsonify({"ok": False, "error": "This token is not transferable"}), 403

    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify({"ok": False, "error": "Sender address not found"}), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify({"ok": False, "error": "Send not enabled for this address"}), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify({"ok": False, "error": "Passphrase required"}), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"ok": False, "error": "Invalid authentication"}), 403

    # Check custom token balance
    token_ledger = load_custom_token_ledger(token["id"])
    sender_token_balance = float(token_ledger.get(from_thr, 0.0))

    if sender_token_balance < amount:
        return jsonify({
            "ok": False,
            "error": f"Insufficient {symbol} balance",
            "balance": round(sender_token_balance, token["decimals"]),
            "required": amount
        }), 400

    # Calculate fee in THR based on the token amount
    # We use a base fee calculation - tokens are treated equivalently to THR for fee purposes
    # This ensures all tokens use the same fee structure
    if speed == "slow":
        thr_fee = round(max(0.001, amount * 0.0009), 6)  # 0.09% minimum 0.001 THR
    else:
        thr_fee = round(max(0.001, calculate_dynamic_fee(amount)), 6)  # Dynamic fee, minimum 0.001 THR

    # Check THR balance for fee
    thr_ledger = load_json(LEDGER_FILE, {})
    sender_thr_balance = float(thr_ledger.get(from_thr, 0.0))

    if sender_thr_balance < thr_fee:
        return jsonify({
            "ok": False,
            "error": "Insufficient THR balance for transaction fee",
            "thr_balance": round(sender_thr_balance, 6),
            "fee_required": thr_fee,
            "token_balance": round(sender_token_balance, token["decimals"])
        }), 400

    # Deduct THR fee from sender (burn it)
    thr_ledger[from_thr] = round(sender_thr_balance - thr_fee, 6)
    save_json(LEDGER_FILE, thr_ledger)

    # Transfer the custom token
    token_ledger[from_thr] = round(sender_token_balance - amount, token["decimals"])
    token_ledger[to_thr] = round(float(token_ledger.get(to_thr, 0.0)) + amount, token["decimals"])
    save_custom_token_ledger(token["id"], token_ledger)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"TOKEN_TRANSFER-{symbol}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_transfer",
        "token_symbol": symbol,
        "token_id": token["id"],
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, token["decimals"]),
        "fee_burned_thr": thr_fee,
        "speed": speed,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain = load_json(CHAIN_FILE, [])
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    logger.info(f"Token transfer: {amount} {symbol} from {from_thr[:10]}... to {to_thr[:10]}... (fee: {thr_fee} THR)")

    return jsonify({
        "ok": True,
        "status": "confirmed",
        "tx": tx,
        "new_balance": token_ledger[from_thr],
        "new_thr_balance": thr_ledger[from_thr],
        "fee_burned": thr_fee
    }), 200


# ─── TOKEN HOLDERS API ─────────────────────────────
@app.route("/api/tokens/<symbol>/holders")
def api_token_holders(symbol):
    """Get list of token holders and count."""
    symbol = symbol.upper()

    # Handle core tokens
    if symbol == "THR":
        ledger = load_json(LEDGER_FILE, {})
        holders = []
        for addr, balance in ledger.items():
            if float(balance) > 0:
                holders.append({"address": addr, "balance": float(balance)})
        holders.sort(key=lambda x: x["balance"], reverse=True)
        total_supply = sum(h["balance"] for h in holders)
        return jsonify({
            "ok": True,
            "symbol": "THR",
            "holders_count": len(holders),
            "total_supply": round(total_supply, 6),
            "holders": holders[:100]  # Top 100 holders
        }), 200

    # Handle custom tokens
    tokens = load_custom_tokens()
    token = tokens.get(symbol)
    if not token:
        return jsonify({"ok": False, "error": f"Token {symbol} not found"}), 404

    ledger = load_custom_token_ledger(token["id"])
    holders = []
    for addr, balance in ledger.items():
        if float(balance) > 0:
            holders.append({"address": addr, "balance": float(balance)})
    holders.sort(key=lambda x: x["balance"], reverse=True)

    return jsonify({
        "ok": True,
        "symbol": symbol,
        "name": token["name"],
        "holders_count": len(holders),
        "total_supply": token.get("total_supply", 0),
        "holders": holders[:100]  # Top 100 holders
    }), 200


@app.route("/api/tokens/stats")
def api_tokens_stats():
    """Get stats for all tokens including holder counts."""
    stats = []

    # THR stats
    thr_ledger = load_json(LEDGER_FILE, {})
    thr_holders = sum(1 for b in thr_ledger.values() if float(b) > 0)
    thr_supply = sum(float(b) for b in thr_ledger.values())
    stats.append({
        "symbol": "THR",
        "name": "Thronos",
        "holders_count": thr_holders,
        "total_supply": round(thr_supply, 6),
        "color": "#ff6600"
    })

    # Custom tokens stats
    tokens = load_custom_tokens()
    for symbol, token in tokens.items():
        ledger = load_custom_token_ledger(token["id"])
        holders = sum(1 for b in ledger.values() if float(b) > 0)
        stats.append({
            "symbol": symbol,
            "name": token["name"],
            "holders_count": holders,
            "total_supply": token.get("total_supply", 0),
            "color": token.get("color", "#00ff66"),
            "logo": token.get("logo")
        })

    return jsonify({"ok": True, "tokens": stats}), 200


@app.route("/send_thr", methods=["POST"])
def send_thr():
    data = request.get_json() or {}
    from_thr=(data.get("from_thr") or "").strip()
    to_thr=(data.get("to_thr") or "").strip()
    amount_raw=data.get("amount",0)
    auth_secret=(data.get("auth_secret") or "").strip()
    passphrase=(data.get("passphrase") or "").strip()
    speed=(data.get("speed") or "fast").strip().lower()  # New: slow or fast

    # Validate THR addresses
    if not validate_thr_address(from_thr):
        return jsonify(error="invalid_from_address", message="Invalid THR address format"),400
    if not validate_thr_address(to_thr):
        return jsonify(error="invalid_to_address", message="Invalid THR address format"),400

    # Validate amount
    valid, error_msg = validate_amount(amount_raw)
    if not valid:
        return jsonify(error="invalid_amount", message=error_msg),400

    try:
        amount=float(amount_raw)
    except (TypeError,ValueError):
        return jsonify(error="invalid_amount"),400
    if not auth_secret:
        return jsonify(error="missing_auth_secret"),400
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==from_thr),None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"),404
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"),400
    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"),400
        auth_string=f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string=f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(error="invalid_auth"),403

    # --- Fee Calculation Based on Speed ---
    if speed == "slow":
        # Slow transactions: 0.09% fee
        fee = round(amount * 0.0009, 6)
        confirmation_policy = "SLOW"
    else:
        # Fast transactions: Use dynamic fee calculation
        fee = calculate_dynamic_fee(amount)
        confirmation_policy = "FAST"

    total_cost = amount + fee

    ledger=load_json(LEDGER_FILE,{})
    sender_balance=float(ledger.get(from_thr,0.0))

    if sender_balance<total_cost:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance,6),
            required=total_cost,
            fee=fee
        ),400
    ledger[from_thr]=round(sender_balance-total_cost,6)
    save_json(LEDGER_FILE,ledger)
    chain=load_json(CHAIN_FILE,[])
    tx={
        "type":"transfer",
        "height":None,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from":from_thr,
        "to":to_thr,
        "amount":round(amount,6),
        "fee_burned":fee,
        "tx_id":f"TX-{len(chain)}-{int(time.time())}",
        "thr_address":from_thr,
        "status":"pending",
        "confirmation_policy": confirmation_policy,
        "min_signers": 1,
        "speed": speed
    }
    pool=load_mempool()
    pool.append(tx)
    save_mempool(pool)
    update_last_block(tx, is_block=False)
    # Broadcast the new pending transaction to peers.  Best effort –
    # failures are ignored.
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="pending", tx=tx, new_balance_from=ledger[from_thr], fee_burned=fee), 200

# ─── SEND CUSTOM TOKENS API ────────────────────────────────────
@app.route("/api/send_token", methods=["POST"])
def send_token():
    """
    Send custom tokens (like JAM, DOGE, etc.) with fee.

    Request body:
    {
        "token_symbol": "JAM",
        "from_thr": "THR...",
        "to_thr": "THR...",
        "amount": 100.0,
        "auth_secret": "...",
        "passphrase": "...",  // optional
        "speed": "fast"  // or "slow"
    }
    """
    data = request.get_json() or {}
    token_symbol = (data.get("token_symbol") or "").upper().strip()
    from_thr = (data.get("from_thr") or "").strip()
    to_thr = (data.get("to_thr") or "").strip()
    amount_raw = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    speed = (data.get("speed") or "fast").strip().lower()

    # Validate inputs
    if not token_symbol:
        return jsonify(error="missing_token_symbol"), 400
    if not validate_thr_address(from_thr):
        return jsonify(error="invalid_from_address"), 400
    if not validate_thr_address(to_thr):
        return jsonify(error="invalid_to_address"), 400

    valid, error_msg = validate_amount(amount_raw)
    if not valid:
        return jsonify(error="invalid_amount", message=error_msg), 400

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid_amount"), 400

    if not auth_secret:
        return jsonify(error="missing_auth_secret"), 400

    # Authenticate sender
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(error="invalid_auth"), 403

    # Calculate fee (same as THR transfers)
    if speed == "slow":
        fee = round(amount * 0.0009, 6)  # 0.09% fee
        confirmation_policy = "SLOW"
    else:
        fee = calculate_dynamic_fee(amount)
        confirmation_policy = "FAST"

    total_cost = amount + fee

    # Load token balances
    token_balances = load_token_balances()

    # Check if token exists
    if token_symbol not in token_balances:
        return jsonify(error="token_not_found", message=f"Token {token_symbol} does not exist"), 404

    sender_balance = float(token_balances[token_symbol].get(from_thr, 0.0))

    if sender_balance < total_cost:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance, 6),
            required=total_cost,
            fee=fee
        ), 400

    # Deduct from sender (including fee)
    token_balances[token_symbol][from_thr] = round(sender_balance - total_cost, 6)

    # Credit receiver (without fee - fee is burned)
    token_balances[token_symbol][to_thr] = round(float(token_balances[token_symbol].get(to_thr, 0.0)) + amount, 6)

    save_token_balances(token_balances)

    # Record transaction in chain
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "token_transfer",
        "token_symbol": token_symbol,
        "height": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, 6),
        "fee_burned": fee,
        "tx_id": f"TOKEN-TX-{len(chain)}-{int(time.time())}",
        "thr_address": from_thr,
        "status": "pending",
        "confirmation_policy": confirmation_policy,
        "min_signers": 1,
        "speed": speed
    }

    pool = load_mempool()
    pool.append(tx)
    save_mempool(pool)
    update_last_block(tx, is_block=False)

    try:
        broadcast_tx(tx)
    except Exception:
        pass

    return jsonify(
        status="pending",
        tx=tx,
        new_balance_from=token_balances[token_symbol][from_thr],
        fee_burned=fee
    ), 200

# ─── REAL-TIME PRICES API (for DEX/Bridge) ────────────────────────────
# Using Google AI grounding + external APIs for accurate pricing

# Price cache to avoid hitting APIs too frequently
_price_cache = {}
_price_cache_ttl = 60  # 60 seconds cache

def get_cached_price(key):
    """Get price from cache if not expired"""
    if key in _price_cache:
        data, timestamp = _price_cache[key]
        if time.time() - timestamp < _price_cache_ttl:
            return data
    return None

def set_cached_price(key, data):
    """Set price in cache with timestamp"""
    _price_cache[key] = (data, time.time())

def fetch_btc_price():
    """Fetch BTC price from CoinGecko API"""
    cached = get_cached_price("btc_usd")
    if cached:
        return cached
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd,eur"},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json().get("bitcoin", {})
            set_cached_price("btc_usd", data)
            return data
    except Exception as e:
        logger.warning(f"Failed to fetch BTC price: {e}")
    return {"usd": 0, "eur": 0}

def fetch_precious_metals_prices():
    """
    Fetch precious metals prices (Gold, Silver, Platinum, Palladium)
    Using metalpriceapi.com free tier or fallback to cached/estimated values
    """
    cached = get_cached_price("metals")
    if cached:
        return cached

    # Try to use Google AI grounding for real-time data
    if ai_agent and ai_agent.gemini_enabled:
        try:
            import google.generativeai as genai
            # Use Gemini with Google Search grounding for live prices
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                "What are the current spot prices (USD per troy ounce) for: Gold (XAU), Silver (XAG), Platinum (XPT), Palladium (XPD)? "
                "Return ONLY a JSON object with these exact keys: gold, silver, platinum, palladium with numeric USD values. No explanation.",
                generation_config={"temperature": 0}
            )
            text = response.text.strip()
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                prices = json.loads(json_match.group())
                # Validate numeric values
                if all(isinstance(prices.get(k), (int, float)) for k in ["gold", "silver", "platinum", "palladium"]):
                    set_cached_price("metals", prices)
                    return prices
        except Exception as e:
            logger.warning(f"Gemini metals price fetch failed: {e}")

    # Fallback to estimated/cached values based on typical market prices
    fallback_prices = {
        "gold": 2650.00,      # XAU/USD typical range
        "silver": 31.50,      # XAG/USD typical range
        "platinum": 980.00,   # XPT/USD typical range
        "palladium": 1050.00  # XPD/USD typical range
    }
    return fallback_prices

@app.route("/api/prices", methods=["GET"])
def api_prices():
    """
    Get real-time prices for DEX/Bridge operations.
    Supports: BTC, Gold, Silver, Platinum, Palladium, THR

    Query params:
        - assets: comma-separated list (e.g., "btc,gold,silver")
        - vs_currency: USD or EUR (default: USD)

    Returns:
        {
            "prices": { "btc": 95000, "gold": 2650, ... },
            "timestamp": 1234567890,
            "source": "live" or "cached"
        }
    """
    try:
        assets_param = request.args.get("assets", "btc,gold,silver,platinum,palladium,thr")
        vs_currency = request.args.get("vs_currency", "usd").lower()
        assets = [a.strip().lower() for a in assets_param.split(",")]

        prices = {}
        source = "live"

        # BTC price
        if "btc" in assets or "bitcoin" in assets:
            btc_data = fetch_btc_price()
            prices["btc"] = btc_data.get(vs_currency, btc_data.get("usd", 0))
            if get_cached_price("btc_usd"):
                source = "cached"

        # Precious metals
        metals_needed = set(assets) & {"gold", "silver", "platinum", "palladium", "xau", "xag", "xpt", "xpd"}
        if metals_needed:
            metals_data = fetch_precious_metals_prices()
            if "gold" in assets or "xau" in assets:
                prices["gold"] = metals_data.get("gold", 0)
            if "silver" in assets or "xag" in assets:
                prices["silver"] = metals_data.get("silver", 0)
            if "platinum" in assets or "xpt" in assets:
                prices["platinum"] = metals_data.get("platinum", 0)
            if "palladium" in assets or "xpd" in assets:
                prices["palladium"] = metals_data.get("palladium", 0)

        # THR price (from internal pool rates or fixed)
        if "thr" in assets:
            # Calculate THR price based on BTC rate in swap
            btc_price = prices.get("btc", 95000)
            thr_rate = 0.0001  # 1 THR = 0.0001 BTC from swap
            prices["thr"] = round(btc_price * thr_rate, 4)

        return jsonify({
            "prices": prices,
            "vs_currency": vs_currency,
            "timestamp": int(time.time()),
            "source": source
        }), 200

    except Exception as e:
        logger.error(f"Prices API error: {e}")
        return jsonify(error=str(e)), 500


@app.route("/api/prices/convert", methods=["GET"])
def api_prices_convert():
    """
    Convert amounts between assets using real-time prices.

    Query params:
        - from_asset: source asset (btc, gold, silver, thr, usd)
        - to_asset: target asset
        - amount: amount to convert

    Returns:
        {
            "from_asset": "btc",
            "to_asset": "gold",
            "from_amount": 1.0,
            "to_amount": 35.85,
            "rate": 35.85,
            "timestamp": 1234567890
        }
    """
    try:
        from_asset = request.args.get("from_asset", "").lower()
        to_asset = request.args.get("to_asset", "").lower()
        try:
            amount = float(request.args.get("amount", 1))
        except:
            amount = 1.0

        if not from_asset or not to_asset:
            return jsonify(error="from_asset and to_asset required"), 400

        # Get all needed prices in USD
        prices_resp = api_prices()
        if prices_resp[1] != 200:
            return prices_resp

        prices = prices_resp[0].get_json().get("prices", {})

        # USD is base currency with price = 1
        prices["usd"] = 1.0
        prices["eur"] = 0.92  # Approximate EUR rate

        from_price = prices.get(from_asset)
        to_price = prices.get(to_asset)

        if from_price is None:
            return jsonify(error=f"Unknown asset: {from_asset}"), 400
        if to_price is None:
            return jsonify(error=f"Unknown asset: {to_asset}"), 400
        if to_price == 0:
            return jsonify(error=f"Cannot convert to {to_asset}: price is 0"), 400

        # Convert: amount * from_price_usd / to_price_usd
        to_amount = (amount * from_price) / to_price
        rate = from_price / to_price

        return jsonify({
            "from_asset": from_asset,
            "to_asset": to_asset,
            "from_amount": amount,
            "to_amount": round(to_amount, 8),
            "rate": round(rate, 8),
            "timestamp": int(time.time())
        }), 200

    except Exception as e:
        logger.error(f"Price convert error: {e}")
        return jsonify(error=str(e)), 500


# ─── SWAP API ──────────────────────────────────────
@app.route("/api/swap", methods=["POST"])
def api_swap():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    secret = data.get("secret")
    
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return jsonify(status="error", message="Invalid amount"), 400
        
    direction = data.get("direction") # THR_TO_BTC or BTC_TO_THR
    
    if not wallet or not secret or amount <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    # Verify Auth (Reusing logic from send_thr)
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==wallet),None)
    if not sender_pledge:
        return jsonify(status="error", message="Unknown wallet"), 404
    
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    
    # Try both auth methods (with and without passphrase) if possible, 
    # but here we only have 'secret'. 
    # If user has passphrase, this simple swap UI might fail. 
    # For now, we assume standard auth.
    auth_string=f"{secret}:auth" 
    
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(status="error", message="Invalid secret (or passphrase required)"), 403

    ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    chain = load_json(CHAIN_FILE, [])

    RATE = 0.0001 # 1 THR = 0.0001 BTC
    SWAP_FEE_PERCENT = 0.003 # 0.3% fee (like Uniswap)

    tx_id = f"SWAP-{int(time.time())}-{secrets.token_hex(4)}"
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    if direction == "THR_TO_BTC":
        # Burn THR, Mint wBTC
        thr_bal = float(ledger.get(wallet, 0.0))
        if thr_bal < amount:
            return jsonify(status="error", message="Insufficient THR"), 400

        btc_out = amount * RATE
        # Apply 0.3% fee
        fee_amount = btc_out * SWAP_FEE_PERCENT
        btc_out_after_fee = btc_out - fee_amount

        ledger[wallet] = round(thr_bal - amount, 6)
        wbtc_ledger[wallet] = round(float(wbtc_ledger.get(wallet, 0.0)) + btc_out_after_fee, 8)
        
        # Log TX
        tx = {
            "type": "swap",
            "from": wallet,
            "to": SWAP_POOL_ADDRESS,
            "amount_in": amount,
            "token_in": "THR",
            "amount_out": btc_out_after_fee,
            "fee": fee_amount,
            "fee_percent": SWAP_FEE_PERCENT,
            "token_out": "wBTC",
            "tx_id": tx_id,
            "timestamp": ts,
            "status": "confirmed" # Instant swap
        }

    elif direction == "BTC_TO_THR":
        # Burn wBTC, Mint THR
        wbtc_bal = float(wbtc_ledger.get(wallet, 0.0))
        if wbtc_bal < amount:
            return jsonify(status="error", message="Insufficient wBTC"), 400

        thr_out = amount / RATE
        # Apply 0.3% fee
        fee_amount = thr_out * SWAP_FEE_PERCENT
        thr_out_after_fee = thr_out - fee_amount

        wbtc_ledger[wallet] = round(wbtc_bal - amount, 8)
        ledger[wallet] = round(float(ledger.get(wallet, 0.0)) + thr_out_after_fee, 6)

        tx = {
            "type": "swap",
            "from": wallet,
            "to": SWAP_POOL_ADDRESS,
            "amount_in": amount,
            "token_in": "wBTC",
            "amount_out": thr_out_after_fee,
            "fee": fee_amount,
            "fee_percent": SWAP_FEE_PERCENT,
            "token_out": "THR",
            "tx_id": tx_id,
            "timestamp": ts,
            "status": "confirmed"
        }
    else:
        return jsonify(status="error", message="Invalid direction"), 400

    save_json(LEDGER_FILE, ledger)
    save_json(WBTC_LEDGER_FILE, wbtc_ledger)
    
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    return jsonify(status="success", tx_id=tx_id), 200

# ─── Token Balances API (NEW) ─────────────────────────────────────
#
# This endpoint returns all balances for custom tokens held by the
# specified THR address.  The response is a dictionary keyed by token
# symbol with the raw float balance.  If the address holds no balance
# for a given token, that token will simply be absent from the result.
@app.route("/api/v1/token_balances/<thr_addr>", methods=["GET"])
def api_v1_token_balances(thr_addr: str):
    """
    Return balances for all issued tokens for the given THR address.

    Example response:
    {
        "THR": 123.456,
        "DOGE": 7890.0
    }

    Decimals are not applied on the backend; the frontend can use the
    decimals from the token registry for display purposes.
    """
    balances = load_token_balances()
    result = {}
    for sym, addr_balances in balances.items():
        try:
            bal = float(addr_balances.get(thr_addr, 0.0))
        except Exception:
            bal = 0.0
        if bal > 0:
            result[sym] = bal
    return jsonify(address=thr_addr, token_balances=result), 200

# ─── GATEWAY API (REAL STRIPE + WITHDRAWALS) ───────────────────────
#
# COMPLIANCE NOTES:
# - THR is sold as a UTILITY TOKEN for use within the Thronos ecosystem
#   (AI credits, network fees, staking) - NOT as an investment/security
# - Stripe TOS allows digital goods and services sales
# - Transaction limits help comply with AML requirements
# - Users must accept terms before purchase
#
GATEWAY_MIN_AMOUNT = 10.0     # Minimum $10 purchase
GATEWAY_MAX_AMOUNT = 5000.0   # Maximum $5000 per transaction (Stripe limits)
GATEWAY_DAILY_LIMIT = 10000.0 # Maximum $10,000 per wallet per day

# Track daily gateway purchases per wallet
GATEWAY_DAILY_FILE = os.path.join(DATA_DIR, "gateway_daily.json")

def load_gateway_daily():
    return load_json(GATEWAY_DAILY_FILE, {})

def save_gateway_daily(data):
    save_json(GATEWAY_DAILY_FILE, data)

def get_daily_total(wallet):
    """Get total gateway purchases for wallet in current UTC day"""
    daily = load_gateway_daily()
    today = time.strftime("%Y-%m-%d", time.gmtime())
    wallet_data = daily.get(wallet, {})
    if wallet_data.get("date") != today:
        return 0.0
    return wallet_data.get("total", 0.0)

def record_daily_purchase(wallet, amount):
    """Record a gateway purchase for daily limit tracking"""
    daily = load_gateway_daily()
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if wallet not in daily or daily[wallet].get("date") != today:
        daily[wallet] = {"date": today, "total": 0.0}
    daily[wallet]["total"] = daily[wallet].get("total", 0.0) + amount
    save_gateway_daily(daily)

@app.route("/api/gateway/create-checkout-session", methods=["POST"])
def create_checkout_session():
    if not stripe:
        return jsonify(error="Stripe not configured"), 503

    data = request.get_json() or {}
    wallet = data.get("wallet")
    fiat_amount = data.get("fiat_amount")
    terms_accepted = data.get("terms_accepted", False)

    if not wallet or not fiat_amount:
        return jsonify(error="Missing parameters"), 400

    # Require terms acceptance for compliance
    if not terms_accepted:
        return jsonify(error="You must accept the Terms of Service to proceed"), 400

    try:
        amount = float(fiat_amount)
    except (ValueError, TypeError):
        return jsonify(error="Invalid amount"), 400

    # Enforce transaction limits
    if amount < GATEWAY_MIN_AMOUNT:
        return jsonify(error=f"Minimum purchase is ${GATEWAY_MIN_AMOUNT}"), 400
    if amount > GATEWAY_MAX_AMOUNT:
        return jsonify(error=f"Maximum purchase is ${GATEWAY_MAX_AMOUNT} per transaction"), 400

    # Check daily limit
    daily_total = get_daily_total(wallet)
    if daily_total + amount > GATEWAY_DAILY_LIMIT:
        remaining = max(0, GATEWAY_DAILY_LIMIT - daily_total)
        return jsonify(
            error=f"Daily limit of ${GATEWAY_DAILY_LIMIT} would be exceeded. Remaining today: ${remaining:.2f}"
        ), 400

    try:
        # Calculate THR amount for display (1 THR = $10)
        thr_amount = amount / 10.0

        # Create Stripe Checkout Session with compliance metadata
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Thronos (THR) Utility Token',
                        'description': f'Purchase {thr_amount:.2f} THR utility tokens for use within the Thronos ecosystem (AI services, network fees, staking). Not a security or investment product.',
                    },
                    'unit_amount': int(amount * 100),  # Cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=DOMAIN_URL + '/gateway?status=success&session_id={CHECKOUT_SESSION_ID}',
            cancel_url=DOMAIN_URL + '/gateway?status=cancel',
            metadata={
                'wallet': wallet,
                'type': 'buy_thr',
                'thr_amount': str(thr_amount),
                'terms_accepted': 'true',
                'timestamp': str(int(time.time()))
            }
        )

        # Record this as a pending purchase for daily limit tracking
        # (will be confirmed/reverted based on webhook)
        record_daily_purchase(wallet, amount)

        return jsonify(id=session.id, thr_amount=thr_amount)
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return jsonify(error=str(e)), 400


@app.route("/api/gateway/limits", methods=["GET"])
def api_gateway_limits():
    """
    Get gateway transaction limits and current daily usage for a wallet.
    """
    wallet = request.args.get("wallet", "")
    daily_total = get_daily_total(wallet) if wallet else 0.0

    return jsonify({
        "min_amount": GATEWAY_MIN_AMOUNT,
        "max_amount": GATEWAY_MAX_AMOUNT,
        "daily_limit": GATEWAY_DAILY_LIMIT,
        "daily_used": daily_total,
        "daily_remaining": max(0, GATEWAY_DAILY_LIMIT - daily_total),
        "thr_rate": 10.0,  # $10 per THR
        "currency": "USD"
    }), 200


# ============================================================================
# IoT Stripe Checkout Endpoint
# ============================================================================
@app.route("/api/stripe/create-checkout", methods=["POST"])
def api_stripe_iot_checkout():
    """
    Create Stripe checkout session for IoT Node Pack purchases.
    Used by the IoT page for hardware pack purchases.
    """
    if not stripe:
        return jsonify(error="Stripe not configured"), 503

    data = request.get_json() or {}
    wallet = data.get("wallet")
    pack_id = data.get("pack_id")
    price_cents = data.get("price_cents")

    if not wallet:
        return jsonify(error="Wallet address required"), 400
    if not pack_id:
        return jsonify(error="Pack ID required"), 400
    if not price_cents or price_cents <= 0:
        return jsonify(error="Invalid price"), 400

    # Pack definitions
    PACK_NAMES = {
        "starter_vehicle": "Starter Vehicle Pack - OBD-II Node",
        "smart_home": "Smart Home Bundle - Gateway + Sensors",
        "industrial": "Industrial Pro Pack - Gateway + Sensors + PLC Kit"
    }

    pack_name = PACK_NAMES.get(pack_id, f"IoT Pack: {pack_id}")
    price_euros = price_cents / 100.0

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': pack_name,
                        'description': f'Thronos IoT Node Pack for earning THR rewards. Hardware will be shipped after payment confirmation.',
                    },
                    'unit_amount': int(price_cents),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=DOMAIN_URL + '/iot?status=success&session_id={CHECKOUT_SESSION_ID}',
            cancel_url=DOMAIN_URL + '/iot?status=cancel',
            metadata={
                'wallet': wallet,
                'type': 'iot_pack',
                'pack_id': pack_id,
                'price_eur': str(price_euros),
                'timestamp': str(int(time.time()))
            }
        )

        return jsonify(url=session.url, id=session.id)
    except Exception as e:
        logger.error(f"Stripe IoT checkout error: {e}")
        return jsonify(error=str(e)), 400

@app.route("/api/gateway/webhook", methods=["POST"])
def stripe_webhook():
    if not stripe:
        return jsonify(status="ignored"), 200
        
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return jsonify(error="Invalid payload"), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify(error="Invalid signature"), 400

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        
        if metadata.get('type') == 'buy_thr':
            wallet = metadata.get('wallet')
            amount_paid_cents = session.get('amount_total', 0)
            fiat_amount = amount_paid_cents / 100.0
            
            # Rate: 1 THR = $10
            thr_amount = fiat_amount / 10.0
            
            # Mint/Send THR
            ledger = load_json(LEDGER_FILE, {})
            ledger[wallet] = round(float(ledger.get(wallet, 0.0)) + thr_amount, 6)
            save_json(LEDGER_FILE, ledger)
            
            chain = load_json(CHAIN_FILE, [])
            tx = {
                "type": "fiat_buy",
                "from": "STRIPE_GATEWAY",
                "to": wallet,
                "amount": thr_amount,
                "fiat_amount": fiat_amount,
                "currency": "USD",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "tx_id": f"BUY-{int(time.time())}-{secrets.token_hex(4)}",
                "status": "confirmed",
                "stripe_id": session.get('id')
            }
            chain.append(tx)
            save_json(CHAIN_FILE, chain)
            update_last_block(tx, is_block=False)
            print(f"💰 Stripe Payment: {fiat_amount} USD -> {thr_amount} THR to {wallet}")

    return jsonify(status="success"), 200

@app.route("/api/gateway/sell", methods=["POST"])
def api_gateway_sell():
    """
    Handles Withdrawal Requests.
    1. Verifies balance & Auth.
    2. Burns THR immediately.
    3. Saves withdrawal request to withdrawals.json for Admin processing.
    """
    data = request.get_json() or {}
    wallet = data.get("wallet")
    secret = data.get("secret")
    
    try:
        thr_amount = float(data.get("thr_amount", 0))
    except (ValueError, TypeError):
        return jsonify(status="error", message="Invalid amount"), 400
        
    bank_info = data.get("bank_info", {})
    if not bank_info.get("iban") or not bank_info.get("name"):
        return jsonify(status="error", message="Missing bank details"), 400
    
    if not wallet or not secret or thr_amount <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    # Verify Auth
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==wallet),None)
    if not sender_pledge:
        return jsonify(status="error", message="Unknown wallet"), 404
    
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    auth_string=f"{secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(status="error", message="Invalid secret"), 403
        
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(wallet, 0.0))
    
    if balance < thr_amount:
        return jsonify(status="error", message="Insufficient THR"), 400
        
    # Rate: 1 THR = $9.8 (Sell Rate)
    rate = 9.8
    fiat_out = thr_amount * rate
    
    # Burn THR
    ledger[wallet] = round(balance - thr_amount, 6)
    ledger[BURN_ADDRESS] = round(float(ledger.get(BURN_ADDRESS, 0.0)) + thr_amount, 6)
    save_json(LEDGER_FILE, ledger)
    
    # Record TX
    chain = load_json(CHAIN_FILE, [])
    tx_id = f"SELL-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "fiat_sell_request",
        "from": wallet,
        "to": "FIAT_GATEWAY",
        "amount": thr_amount,
        "fiat_amount": fiat_out,
        "currency": "USD",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": tx_id,
        "status": "processing_withdrawal"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    # Save Withdrawal Request
    withdrawals = load_json(WITHDRAWALS_FILE, [])
    withdrawals.append({
        "id": tx_id,
        "wallet": wallet,
        "thr_amount": thr_amount,
        "fiat_amount": fiat_out,
        "bank_details": { # Normalized key name to match admin panel
            "holder": bank_info.get("name"),
            "iban": bank_info.get("iban"),
            "bic": bank_info.get("bic")
        },
        "bank_info": bank_info, # Keep original for compatibility
        "timestamp": tx["timestamp"],
        "status": "pending_admin_review", # Normalized status
        "fiat_estimated": fiat_out
    })
    save_json(WITHDRAWALS_FILE, withdrawals)
    
    return jsonify(status="success", tx_id=tx_id, fiat_amount=fiat_out, message="Withdrawal request submitted. Funds will be wired within 24h."), 200


# ─── ADMIN WHITELIST + MIGRATION ───────────────────
@app.route("/admin/whitelist", methods=["GET"])
def admin_whitelist_page():
    secret=request.args.get("secret","")
    if secret!=ADMIN_SECRET:
        return "Forbidden (wrong or missing secret)",403
    return render_template("admin_whitelist.html", admin_secret=secret)

@app.route("/admin/whitelist/add", methods=["POST"])
def admin_whitelist_add():
    data=request.get_json() or {}
    if data.get("secret")!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    btc=(data.get("btc_address") or "").strip()
    if not btc:
        return jsonify(error="missing_btc_address"),400
    wl=load_json(WHITELIST_FILE,[])
    if btc not in wl:
        wl.append(btc)
        save_json(WHITELIST_FILE, wl)
    return jsonify(status="ok",whitelist=wl),200

@app.route("/admin/whitelist/list", methods=["GET"])
def admin_whitelist_list():
    secret=request.args.get("secret","")
    if secret!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    return jsonify(whitelist=load_json(WHITELIST_FILE,[])),200

@app.route("/admin/migrate_seeds", methods=["POST","GET"])
def admin_migrate_seeds():
    payload=request.get_json() or {}
    secret=request.args.get("secret","") or payload.get("secret","")
    if secret!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    pledges=load_json(PLEDGE_CHAIN,[])
    changed=[]
    for p in pledges:
        if p.get("send_seed_hash") and p.get("send_auth_hash"):
            continue
        thr_addr=p["thr_address"]
        btc_address=p["btc_address"]
        pledge_text=p["pledge_text"]
        pledge_hash=p["pledge_hash"]
        send_seed=secrets.token_hex(16)
        send_seed_hash=hashlib.sha256(send_seed.encode()).hexdigest()
        send_auth_hash=hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()
        p["send_seed_hash"]=send_seed_hash
        p["send_auth_hash"]=send_auth_hash
        p["has_passphrase"]=False
        chain=load_json(CHAIN_FILE,[])
        height=len(chain)
        pdf_name=create_secure_pdf_contract(
            btc_address, pledge_text, thr_addr, pledge_hash, height, send_seed, CONTRACTS_DIR
        )
        p["pdf_filename"]=pdf_name
        changed.append({
            "thr_address":thr_addr,
            "btc_address":btc_address,
            "send_seed":send_seed,
            "pdf_filename":pdf_name
        })
    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(migrated=changed),200


# ─── QUORUM LAYER – aggregation API surface (BLS placeholder) ───────────────
def _tx_message_bytes(tx: dict) -> bytes:
    material = f"{tx.get('from','')}|{tx.get('to','')}|{tx.get('amount',0)}|{tx.get('tx_id','')}"
    return hashlib.sha256(material.encode()).digest()

@app.route("/api/attest", methods=["POST"])
def api_attest():
    data=request.get_json() or {}
    tx_id=(data.get("tx_id") or "").strip()
    signer=(data.get("signer") or "").strip()
    partial_sig=(data.get("partial_sig") or "").strip()
    pubkey=(data.get("pubkey") or "").strip()
    scheme=(data.get("scheme") or "BLS").upper()
    if not (tx_id and signer and partial_sig and pubkey):
        return jsonify(error="missing_fields"),400
    pool=load_mempool()
    tx=next((t for t in pool if t.get("tx_id")==tx_id),None)
    if not tx:
        chain=load_json(CHAIN_FILE,[])
        tx=next((t for t in chain if t.get("tx_id")==tx_id and t.get("status")!="confirmed"),None)
    if not tx:
        return jsonify(error="unknown_tx"),404
    store=load_attest_store()
    bucket=store.get(tx_id, {"scheme":scheme, "items":[]})
    already={ (i.get("pubkey"), i.get("signer")) for i in bucket["items"] }
    if (pubkey, signer) not in already:
        bucket["items"].append({"signer":signer,"sig":partial_sig,"pubkey":pubkey,"ts":int(time.time())})
        store[tx_id]=bucket
        save_attest_store(store)
    if "signers" not in tx:
        tx["signers"]=[]
    if tx.get("status") not in ("pending","confirmed"):
        tx["status"]="quoruming"
    save_mempool([t if t.get("tx_id")!=tx_id else tx for t in pool])
    return jsonify(status="accepted", collected=len(bucket["items"]), scheme=bucket["scheme"]),200

@app.route("/api/tx/<tx_id>/verify", methods=["GET"])
def api_verify_tx_sig(tx_id):
    pool=load_mempool()
    tx=next((t for t in pool if t.get("tx_id")==tx_id),None)
    if not tx:
        return jsonify(error="unknown_tx"),404
    msg=_tx_message_bytes(tx)
    ok=False
    if tx.get("aggregate_sig") and tx.get("pubkeys"):
        ok=qc_verify(tx["aggregate_sig"], tx["pubkeys"], msg, tx.get("att_scheme","BLS"))
    return jsonify(tx_id=tx_id, verified=bool(ok)),200

def aggregator_step():
    pool=load_mempool()
    if not pool:
        return
    store=load_attest_store()
    changed=False
    for tx in pool:
        if tx.get("status")=="confirmed":
            continue
        policy=(tx.get("confirmation_policy") or "FAST").upper()
        min_signers=int(tx.get("min_signers") or 1)
        bucket=store.get(tx["tx_id"], {"items":[], "scheme":"BLS"})
        items=bucket.get("items",[])
        normalized=[]
        for it in items:
            if not it.get("sig"):
                it["sig"]=it.get("partial_sig")
            if it.get("pubkey") and it.get("sig"):
                normalized.append({
                    "pubkey":it["pubkey"],
                    "sig":it["sig"],
                    "signer":it.get("signer", it.get("pubkey")[:12])
                })
        if not normalized:
            if policy=="FAST":
                if tx.get("status")!="pending":
                    tx["status"]="pending"; changed=True
            else:
                if tx.get("status")!="quoruming":
                    tx["status"]="quoruming"; changed=True
            continue
        if len(normalized) >= min_signers:
            msg=_tx_message_bytes(tx)
            res=qc_aggregate(normalized, bucket.get("scheme","BLS"), msg)
            if res:
                tx["aggregate_sig"]=res.get("agg_sig")
                tx["signers"]=res.get("signers",[])
                tx["pubkeys"]=res.get("pubkeys",[])
                tx["att_scheme"]=res.get("scheme")
                if tx.get("status")!="pending":
                    tx["status"]="pending"
                changed=True
        else:
            if policy=="FAST":
                if tx.get("status")!="pending":
                    tx["status"]="pending"; changed=True
            else:
                if tx.get("status")!="quoruming":
                    tx["status"]="quoruming"; changed=True
    if changed:
        save_mempool(pool)


# ─── MINING ENDPOINT ───────────────────────────────
@app.route("/submit_block", methods=["POST"])
def submit_block():
    data = request.get_json() or {}
    thr_address = data.get("thr_address")
    nonce = data.get("nonce")
    if not thr_address or nonce is None:
        return jsonify(error="Missing mining data"),400
    chain=load_json(CHAIN_FILE,[])
    
    server_last_hash = ""
    blocks=[b for b in chain if isinstance(b,dict) and b.get("reward") is not None]
    if blocks:
        server_last_hash = blocks[-1].get("block_hash","")
    else:
        server_last_hash = "0"*64
        
    is_stratum = "merkle_root" in data
    pow_hash=""
    prev_hash=""
    if is_stratum:
        merkle_root=data.get("merkle_root")
        prev_hash=data.get("prev_hash")
        time_val=data.get("time")
        nbits=data.get("nbits")
        version=data.get("version",1)
        if not all([merkle_root, prev_hash, time_val, nbits]):
            return jsonify(error="Missing Stratum fields"),400
        if prev_hash!=server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"),400
        try:
            header  = struct.pack("<I",version)
            header += bytes.fromhex(prev_hash)[::-1]
            header += bytes.fromhex(merkle_root)[::-1]
            header += struct.pack("<I",time_val)
            header += struct.pack("<I",nbits)
            header += struct.pack("<I",nonce)
            pow_hash = sha256d(header)[::-1].hex()
        except Exception as e:
            return jsonify(error=f"Header construction failed: {e}"),400
    else:
        pow_hash=data.get("pow_hash")
        prev_hash=data.get("prev_hash")
        if prev_hash!=server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"),400
        check=hashlib.sha256((prev_hash+thr_address).encode()+str(nonce).encode()).hexdigest()
        if check!=pow_hash:
            return jsonify(error="Invalid hash calculation"),400
            
    current_target = get_mining_target()
    if int(pow_hash, 16) > current_target:
        return jsonify(error=f"Insufficient difficulty. Target: {hex(current_target)}"), 400

    # Reward split με σωστό height (blocks + offset)
    local_height  = len(blocks)
    height        = HEIGHT_OFFSET + local_height
    total_reward  = calculate_reward(height)
    
    miner_share=round(total_reward*0.80,6)
    ai_share=round(total_reward*0.10,6)
    burn_share=round(total_reward*0.10,6)
    ts=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    new_block={
        "thr_address":thr_address,
        "timestamp":ts,
        "block_hash":pow_hash,
        "prev_hash":prev_hash,
        "nonce":nonce,
        "reward":total_reward,
        "reward_split":{"miner":miner_share,"ai":ai_share,"burn":burn_share},
        "pool_fee":burn_share,
        "reward_to_miner":miner_share,
        "height":height,
        "type":"block",
        "target":current_target,
        "is_stratum":is_stratum
    }
    chain.append(new_block)

    # include mempool TXs
    pool=load_mempool()
    included=[]
    if pool:
        for tx in list(pool):
            tx["height"]=height
            tx["status"]="confirmed"
            tx["timestamp"]=ts
            chain.append(tx)
            included.append(tx)
        save_mempool([])

        ledger=load_json(LEDGER_FILE,{})
        for tx in included:
            if tx.get("type")=="transfer":
                to_thr=tx["to"]
                amt=float(tx["amount"])
                fee=float(tx.get("fee_burned",0.0))
                ledger[to_thr]=round(ledger.get(to_thr,0.0)+amt,6)
                ledger[BURN_ADDRESS]=round(ledger.get(BURN_ADDRESS,0.0)+fee,6)
            elif tx.get("type")=="token_transfer":
                sym = tx.get("symbol")
                tok = get_custom_token(sym)
                amt = float(tx.get("amount", 0.0))
                fee = float(tx.get("fee_burned", 0.0))
                to_addr = tx.get("to")

                # Credit receiver's custom-token balance at block-time (sender already deducted at submit-time).
                if tok and to_addr:
                    tledger = load_custom_token_ledger(tok["id"])
                    tledger[to_addr] = round(float(tledger.get(to_addr, 0.0)) + amt, tok.get("decimals", 8))
                    save_custom_token_ledger(tok["id"], tledger)

                # Account THR fee burn to burn address for transparency.
                ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + fee, 6)

        save_json(LEDGER_FILE,ledger)

    # reward to ledger
    ledger=load_json(LEDGER_FILE,{})
    ledger[thr_address]=round(ledger.get(thr_address,0.0)+miner_share,6)
    ledger[AI_WALLET_ADDRESS]=round(ledger.get(AI_WALLET_ADDRESS,0.0)+ai_share,6)
    ledger[BURN_ADDRESS]=round(ledger.get(BURN_ADDRESS,0.0)+burn_share,6)
    save_json(LEDGER_FILE,ledger)

    save_json(CHAIN_FILE, chain)
    update_last_block(new_block, is_block=True)
    # Broadcast the newly mined block to peers.  This is best‑effort
    # and failures are ignored.  It allows other nodes to update
    # their chains without polling.
    try:
        broadcast_block(new_block)
    except Exception:
        pass
    print(f"⛏️ Miner {thr_address} found block #{height}! R={total_reward} (m/a/b: {miner_share}/{ai_share}/{burn_share}) | TXs: {len(included)} | Stratum={is_stratum}")
    return jsonify(status="accepted", height=height, reward=miner_share, tx_included=len(included)), 200


# ─── BACKGROUND MINTER / WATCHDOG ──────────────────
def submit_mining_block_for_pledge(thr_addr):
    chain = load_json(CHAIN_FILE, [])

    pow_blocks = [
        b for b in chain
        if isinstance(b, dict) and b.get("reward") is not None
    ]

    if pow_blocks:
        prev_hash = pow_blocks[-1].get("block_hash", "0"*64)
        local_height = len(pow_blocks)
    else:
        prev_hash = "0"*64
        local_height = 0

    height       = HEIGHT_OFFSET + local_height
    total_reward = calculate_reward(height)

    miner_share = round(total_reward * 0.80, 6)
    ai_share    = round(total_reward * 0.10, 6)
    burn_share  = round(total_reward * 0.10, 6)

    target = get_mining_target()

    nonce = random.randrange(0, 2**32)
    while True:
        h = hashlib.sha256((prev_hash + thr_addr).encode() + str(nonce).encode()).hexdigest()
        if int(h, 16) <= target:
            pow_hash = h
            break
        nonce = (nonce + 1) % (2**32)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    new_block = {
        "thr_address": thr_addr,
        "timestamp": ts,
        "block_hash": pow_hash,
        "prev_hash": prev_hash,
        "nonce": nonce,
        "reward": total_reward,
        "reward_split": {"miner": miner_share, "ai": ai_share, "burn": burn_share},
        "pool_fee": burn_share,
        "reward_to_miner": miner_share,
        "height": height,
        "type": "block",
        "target": target,
        "is_stratum": False,
    }
    chain.append(new_block)

    pool = load_mempool()
    included = []
    if pool:
        for tx in list(pool):
            tx["height"] = height
            tx["status"] = "confirmed"
            tx["timestamp"] = ts
            chain.append(tx)
            included.append(tx)
        save_mempool([])

        ledger = load_json(LEDGER_FILE, {})
        for tx in included:
            if tx.get("type") == "transfer":
                ledger[tx["to"]] = round(ledger.get(tx["to"], 0.0) + float(tx["amount"]), 6)
                ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + float(tx.get("fee_burned", 0.0)), 6)
        save_json(LEDGER_FILE, ledger)

    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_addr] = round(ledger.get(thr_addr, 0.0) + miner_share, 6)
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + ai_share, 6)
    ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + burn_share, 6)
    save_json(LEDGER_FILE, ledger)

    save_json(CHAIN_FILE, chain)
    update_last_block(new_block, is_block=True)
    print(f"⛏️ [Pledge PoW] block #{height} for {thr_addr} | TXs: {len(included)} | hash={pow_hash[:16]}…")

def seconds_since_last_block()->float:
    chain=load_json(CHAIN_FILE,[])
    blocks=[b for b in chain if isinstance(b,dict) and b.get("reward") is not None]
    if not blocks:
        return 10**9
    try:
        t_fmt="%Y-%m-%d %H:%M:%S UTC"
        last_ts=datetime.strptime(blocks[-1]["timestamp"],t_fmt).timestamp()
        return time.time()-last_ts
    except Exception:
        return 10**9

def confirm_mempool_if_stuck(max_wait_sec:int=180):
    pool=load_mempool()
    if not pool:
        return
    if seconds_since_last_block()<max_wait_sec:
        return
    print("⚠️ Watchdog: Mempool stuck > 3 mins. Auto-mining block to clear TXs.")
    submit_mining_block_for_pledge(AI_WALLET_ADDRESS)

def mint_first_blocks():
    pledges=load_json(PLEDGE_CHAIN,[])
    chain=load_json(CHAIN_FILE,[])
    seen={ b.get("thr_address") for b in chain if isinstance(b,dict) and b.get("thr_address") }
    for p in pledges:
        thr=p["thr_address"]
        if thr in seen:
            continue
        submit_mining_block_for_pledge(thr)


# ─── AI KNOWLEDGE WATCHER – log -> mempool -> block ─────────────────────────
def ai_knowledge_watcher():
    """
    Διαβάζει το AI_BLOCK_LOG_FILE (ai_block_log.json) και για κάθε νέα
    εγγραφή δημιουργεί mempool TX τύπου 'ai_knowledge'.
    Τα TXs αυτά θα μπουν στο επόμενο block που θα γίνει mined.
    """
    try:
        log_entries = load_json(AI_BLOCK_LOG_FILE, [])
        if not log_entries:
            return

        pool = load_mempool()
        chain = load_json(CHAIN_FILE, [])

        seen_ids = set(
            tx.get("ai_log_id") for tx in pool
            if isinstance(tx, dict) and tx.get("type") == "ai_knowledge"
        )
        for tx in chain:
            if isinstance(tx, dict) and tx.get("type") == "ai_knowledge":
                if tx.get("ai_log_id"):
                    seen_ids.add(tx["ai_log_id"])

        changed = False

        for entry in log_entries:
            eid = entry.get("id")
            if not eid or eid in seen_ids:
                continue

            if str(entry.get("status","")).lower() == "error":
                continue

            prompt = entry.get("prompt", "")
            response = entry.get("response", "")
            provider = entry.get("provider", "")
            model = entry.get("model", "")
            wallet = entry.get("wallet") or AI_WALLET_ADDRESS
            ts = entry.get("timestamp") or time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
            )

            payload_obj = {
                "prompt_tail": prompt[-512:],
                "response_tail": response[-2048:],
                "provider": provider,
                "model": model,
            }
            payload_json = json.dumps(payload_obj, ensure_ascii=False)
            ai_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

            tx = {
                "type": "ai_knowledge",
                "height": None,
                "timestamp": ts,
                "from": wallet,
                "to": AI_WALLET_ADDRESS,
                "amount": 0.0,
                "fee_burned": 0.0,
                "tx_id": f"AI-{eid}",
                "ai_log_id": eid,
                "ai_hash": ai_hash,
                "ai_payload": payload_json,
                "status": "pending",
                "confirmation_policy": "FAST",
                "min_signers": 0,
            }

            pool.append(tx)
            seen_ids.add(eid)
            changed = True

        if changed:
            save_mempool(pool)
            print("🤖 [AI-KNOWLEDGE] updated mempool with new AI entries.")

    except Exception as e:
        print("[AI-KNOWLEDGE WATCHER] error:", e)

# ─── CRYPTO HUNTERS P2E API (NEW) ──────────────────
@app.route("/game")
def game_page():
    return render_template("game.html")

@app.route("/api/game/submit_score", methods=["POST"])
def api_game_submit_score():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    score = int(data.get("score", 0))
    
    if not wallet or score <= 0:
        return jsonify(status="error", message="Invalid input"), 400
        
    # Simple logic: Reward = Score * 0.001 THR (capped at 10 THR per claim)
    reward = min(score * 0.001, 10.0)
    
    ledger = load_json(LEDGER_FILE, {})
    chain = load_json(CHAIN_FILE, [])
    
    # Minting logic for Game Rewards (or transfer from pool if we had pre-mined)
    # For now, we mint (inflationary P2E)
    ledger[wallet] = round(float(ledger.get(wallet, 0.0)) + reward, 6)
    save_json(LEDGER_FILE, ledger)
    
    tx = {
        "type": "game_reward",
        "from": GAME_POOL_ADDRESS,
        "to": wallet,
        "amount": reward,
        "score": score,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"GAME-{int(time.time())}-{secrets.token_hex(4)}",
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    return jsonify(status="success", reward=reward, tx_id=tx["tx_id"]), 200

# ─── API v1 ENDPOINTS (NEW in v3.7) ──────────────────────────────────────
#
# These endpoints expose a stable programmatic interface for external
# applications (wallets, explorers, integrations) to interact with the
# Thronos chain.  All endpoints under ``/api/v1`` return JSON responses.

@app.route("/api/v1/balance/<thr_addr>", methods=["GET"])
def api_v1_balance(thr_addr: str):
    """Return the current THR balance for the given address."""
    ledger = load_json(LEDGER_FILE, {})
    try:
        bal = round(float(ledger.get(thr_addr, 0.0)), 6)
    except Exception:
        bal = 0.0
    return jsonify(address=thr_addr, balance=bal), 200


@app.route("/api/v1/address/<thr_addr>/history", methods=["GET"])
def api_v1_address_history(thr_addr: str):
    """Return the on‑chain transaction history for the specified address."""
    chain = load_json(CHAIN_FILE, [])
    history = [
        tx for tx in chain
        if isinstance(tx, dict) and (tx.get("from") == thr_addr or tx.get("to") == thr_addr)
    ]
    return jsonify(address=thr_addr, transactions=history), 200


@app.route("/api/v1/block/<int:height>", methods=["GET"])
def api_v1_block_by_height(height: int):
    """Fetch a block by its height (1‑based, includes HEIGHT_OFFSET).  If
    ``height`` is outside the current chain range, respond with a 404."""
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    idx = height - HEIGHT_OFFSET
    if idx < 0 or idx >= len(blocks):
        return jsonify(error="block_not_found", height=height), 404
    block = blocks[idx]
    return jsonify(block=block, height=height), 200


@app.route("/api/v1/blockhash/<string:block_hash>", methods=["GET"])
def api_v1_block_by_hash(block_hash: str):
    """Fetch a block by its hash.  Returns 404 if no matching block is
    found."""
    chain = load_json(CHAIN_FILE, [])
    block = next(
        (b for b in chain if isinstance(b, dict) and b.get("reward") is not None and b.get("block_hash") == block_hash),
        None,
    )
    if not block:
        return jsonify(error="block_not_found", block_hash=block_hash), 404
    # Derive height for reference
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    height_calc = HEIGHT_OFFSET + blocks.index(block)
    return jsonify(block=block, height=height_calc), 200


@app.route("/api/v1/status", methods=["GET"])
def api_v1_status():
    """Return high‑level network status: current tip, block count, mempool
    size and total supply."""
    last_summary = load_json(LAST_BLOCK_FILE, {})
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    block_count = HEIGHT_OFFSET + len(blocks)
    mempool_len = len(load_mempool())
    total_supply = round(sum(float(v) for v in load_json(LEDGER_FILE, {}).values()), 6)
    return jsonify(
        height=last_summary.get("height"),
        block_hash=last_summary.get("block_hash"),
        timestamp=last_summary.get("timestamp"),
        thr_address=last_summary.get("thr_address"),
        block_count=block_count,
        mempool=mempool_len,
        total_supply=total_supply,
    ), 200


@app.route("/api/v1/submit", methods=["POST"])
def api_v1_submit_transaction():
    """Submit a signed transaction to the node.  Currently supports only
    basic THR transfers.  The expected JSON payload mirrors the fields
    accepted by ``/send_thr``: ``from_thr``, ``to_thr``, ``amount``,
    ``auth_secret``, and optionally ``passphrase``.  Additional keys are
    ignored.  A successful call returns the pending transaction and the
    updated balance of the sender."""
    # We delegate to the ``send_thr`` function which validates and queues
    # transactions in the mempool.  ``send_thr`` uses the global
    # ``request`` context, so we simply return its response.
    return send_thr()


@app.route("/api/v1/peers", methods=["GET"])
def api_v1_get_peers():
    """Return the list of known peer URLs."""
    return jsonify(peers=load_peers()), 200


@app.route("/api/v1/peers", methods=["POST"])
def api_v1_add_peer():
    """Add a new peer URL to the local registry.  Expects a JSON body
    containing a ``url`` field.  Duplicate entries are ignored.  Returns the
    updated list of peers."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="missing_url"), 400
    peers = load_peers()
    if url not in peers:
        peers.append(url)
        save_peers(peers)
    return jsonify(peers=peers), 200


@app.route("/api/v1/receive_tx", methods=["POST"])
def api_v1_receive_tx():
    """Endpoint for peer nodes to push transactions to this node.  The
    incoming transaction should be a JSON object conforming to the Thronos
    transaction schema.  The transaction is appended to the mempool if it
    does not already exist."""
    tx = request.get_json() or {}
    if not isinstance(tx, dict) or not tx.get("tx_id"):
        return jsonify(error="invalid_tx"), 400
    pool = load_mempool()
    if all(t.get("tx_id") != tx.get("tx_id") for t in pool):
        pool.append(tx)
        save_mempool(pool)
    return jsonify(status="accepted"), 200


@app.route("/api/v1/receive_block", methods=["POST"])
def api_v1_receive_block():
    """Endpoint for peer nodes to push newly mined blocks to this node.
    This simple implementation verifies that the incoming object has a
    ``block_hash`` and ``reward`` field before appending it to the chain.  A
    more complete implementation would perform full validation and fork
    resolution."""
    block = request.get_json() or {}
    if not isinstance(block, dict) or not block.get("block_hash") or block.get("reward") is None:
        return jsonify(error="invalid_block"), 400
    chain = load_json(CHAIN_FILE, [])
    if any(b.get("block_hash") == block.get("block_hash") for b in chain if isinstance(b, dict)):
        return jsonify(status="duplicate"), 200
    chain.append(block)
    save_json(CHAIN_FILE, chain)
    thr_addr = block.get("thr_address")
    reward = float(block.get("reward", 0.0))
    if thr_addr:
        ledger = load_json(LEDGER_FILE, {})
        ledger[thr_addr] = round(float(ledger.get(thr_addr, 0.0)) + reward, 6)
        save_json(LEDGER_FILE, ledger)
    update_last_block(block, is_block=True)
    return jsonify(status="added"), 201

# ─── SCHEDULER ─────────────────────────────────────
# Only start scheduler on MASTER nodes (replicas are read-only)
if NODE_ROLE == "master":
    print(f"[SCHEDULER] Starting as MASTER node")
    scheduler=BackgroundScheduler(daemon=True)
    scheduler.add_job(mint_first_blocks, "interval", minutes=1)
    scheduler.add_job(confirm_mempool_if_stuck, "interval", seconds=45)
    scheduler.add_job(aggregator_step, "interval", seconds=10)
    scheduler.add_job(ai_knowledge_watcher, "interval", seconds=30)  # NEW
    scheduler.start()
    print(f"[SCHEDULER] All jobs started")
else:
    print(f"[SCHEDULER] Running as REPLICA - scheduler disabled")
    scheduler = None

    # Start heartbeat sender for replica nodes
    import threading
    import socket

    def send_heartbeat_to_master():
        """Send periodic heartbeat from replica to master"""
        # Generate unique peer_id based on hostname and port
        hostname = socket.gethostname()
        port = os.getenv("PORT", "5000")
        peer_id = f"replica-{hostname}-{port}"

        # Use REPLICA_EXTERNAL_URL if set (for cloud deployments like Railway)
        # Otherwise fall back to hostname:port (for local Docker/testing)
        if REPLICA_EXTERNAL_URL:
            # Ensure it has https:// prefix for Railway domains
            replica_url = REPLICA_EXTERNAL_URL if REPLICA_EXTERNAL_URL.startswith('http') else f"https://{REPLICA_EXTERNAL_URL}"
            peer_id = f"replica-{REPLICA_EXTERNAL_URL.replace('https://', '').replace('http://', '').split('.')[0]}"
        else:
            replica_url = f"http://{hostname}:{port}"

        print(f"[HEARTBEAT] Replica URL configured as: {replica_url}")
        print(f"[HEARTBEAT] Peer ID: {peer_id}")
        print(f"[HEARTBEAT] Master URL: {MASTER_INTERNAL_URL}")

        while True:
            try:
                response = requests.post(
                    f"{MASTER_INTERNAL_URL}/api/peers/heartbeat",
                    json={
                        "peer_id": peer_id,
                        "url": replica_url,
                        "node_role": NODE_ROLE,
                        "timestamp": int(time.time())
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"[HEARTBEAT] Sent to master: {response.json()}")
                else:
                    print(f"[HEARTBEAT] Failed: {response.status_code} - {response.text}")
            except requests.exceptions.ConnectionError as e:
                print(f"[HEARTBEAT] Connection error to master (will retry): {e}")
            except requests.exceptions.Timeout:
                print(f"[HEARTBEAT] Timeout connecting to master (will retry)")
            except Exception as e:
                print(f"[HEARTBEAT] Error sending to master: {e}")

            # Send heartbeat every 30 seconds (TTL is 60s)
            time.sleep(30)

    if MASTER_INTERNAL_URL.startswith("http://localhost"):
        print("[HEARTBEAT] MASTER_INTERNAL_URL not set; heartbeat disabled.")
    else:
        heartbeat_thread = threading.Thread(target=send_heartbeat_to_master, daemon=True)
        heartbeat_thread.start()
        print(f"[HEARTBEAT] Replica heartbeat sender started -> {MASTER_INTERNAL_URL}")

# ─── ADMIN MINT ENDPOINT (NEW) ───────────────────────────────────────
#
# The BTC → THR bridge requires a privileged endpoint to mint new THR
# tokens when a valid deposit is detected on the Bitcoin network.  The
# watcher service calls this endpoint with the appropriate secret and
# target address.  Minted amounts are credited to the specified
# address and recorded on the chain as a 'mint' transaction.  Only
# callers providing the correct ``secret`` (matching ``ADMIN_SECRET``)
# will succeed.

@app.route("/admin/mint", methods=["POST"])
def admin_mint():
    data = request.get_json() or {}
    secret = data.get("secret")
    thr_addr = data.get("thr_address") or data.get("address")
    amount_raw = data.get("amount", 0)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid amount"), 400
    if secret != ADMIN_SECRET:
        return jsonify(status="error", message="Unauthorized"), 403
    if not thr_addr or amount <= 0:
        return jsonify(status="error", message="Missing address or amount"), 400

    # Update ledger
    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_addr] = round(float(ledger.get(thr_addr, 0.0)) + amount, 6)
    save_json(LEDGER_FILE, ledger)

    # Record mint transaction in the chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"MINT-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "mint",
        "from": "mint",
        "to": thr_addr,
        "thr_address": thr_addr,
        "amount": round(amount, 6),
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    # Update last_block summary (treat as a non-block update)
    update_last_block(tx, is_block=False)
    # Optionally broadcast to peers that a mint occurred
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="success", tx_id=tx_id, thr_address=thr_addr, new_balance=ledger[thr_addr]), 201


# ─── L2E API ────────────────────────────────────────────────────────
#
# The Learn‑to‑Earn (L2E) token introduces a second ledger alongside the
# THR ledger.  Students earn L2E tokens for completing courses, and
# teachers or authorized administrators may mint L2E tokens on demand.
# These endpoints mirror the existing THR helper endpoints but operate
# solely on the L2E ledger.  Transfers of L2E are validated for
# sufficient balance and recorded on chain as transactions of type
# ``l2e_transfer``.  Minting is restricted to callers that provide the
# correct ``ADMIN_SECRET``.

@app.route("/api/v1/l2e/balance/<thr_addr>", methods=["GET"])
def api_v1_l2e_balance(thr_addr: str):
    """Return the current L2E balance for the given address."""
    ledger = load_json(L2E_LEDGER_FILE, {})
    try:
        bal = round(float(ledger.get(thr_addr, 0.0)), 6)
    except Exception:
        bal = 0.0
    return jsonify(address=thr_addr, l2e_balance=bal), 200


@app.route("/admin/mint_l2e", methods=["POST"])
def admin_mint_l2e():
    """
    Mint new L2E tokens and credit them to the specified address.  The
    caller must supply the correct ``secret`` (matching ``ADMIN_SECRET``).
    The payload should include ``thr_address`` (or ``address``) and
    ``amount``.  A mint transaction of type ``l2e_mint`` is appended to
    the chain, and the L2E ledger is updated.
    """
    data = request.get_json() or {}
    secret = data.get("secret")
    thr_addr = data.get("thr_address") or data.get("address")
    amount_raw = data.get("amount", 0)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid amount"), 400
    if secret != ADMIN_SECRET:
        return jsonify(status="error", message="Unauthorized"), 403
    if not thr_addr or amount <= 0:
        return jsonify(status="error", message="Missing address or amount"), 400
    # Update L2E ledger
    ledger = load_json(L2E_LEDGER_FILE, {})
    ledger[thr_addr] = round(float(ledger.get(thr_addr, 0.0)) + amount, 6)
    save_json(L2E_LEDGER_FILE, ledger)
    # Record mint transaction in chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"L2E-MINT-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "l2e_mint",
        "from": "mint",
        "to": thr_addr,
        "thr_address": thr_addr,
        "amount": round(amount, 6),
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="success", tx_id=tx_id, thr_address=thr_addr, new_balance=ledger[thr_addr]), 201


@app.route("/send_l2e", methods=["POST"])
def send_l2e():
    """
    Transfer L2E tokens from one address to another.  The payload
    requires ``from_thr``, ``to_thr``, ``amount`` and an ``auth_secret``.
    The sender must have previously created a THR pledge with a send
    secret, which is reused here for L2E transfers.  This simple scheme
    reuses the THR authentication mechanism to authorize L2E spends.
    """
    data = request.get_json() or {}
    from_thr = (data.get("from_thr") or "").strip()
    to_thr = (data.get("to_thr") or "").strip()
    amount_raw = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid_amount"), 400
    if not from_thr or not to_thr:
        return jsonify(error="missing_from_or_to"), 400
    if amount <= 0:
        return jsonify(error="amount_must_be_positive"), 400
    if not auth_secret:
        return jsonify(error="missing_auth_secret"), 400
    # Validate the sender's pledge and auth hash from the THR pledge registry
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"), 404
    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"), 400
    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(error="invalid_auth"), 403
    # Update L2E ledger balances
    ledger = load_json(L2E_LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_thr, 0.0))
    if sender_balance < amount:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance, 6),
            required=amount
        ), 400
    ledger[from_thr] = round(sender_balance - amount, 6)
    ledger[to_thr] = round(float(ledger.get(to_thr, 0.0)) + amount, 6)
    save_json(L2E_LEDGER_FILE, ledger)
    # Record transaction in chain and mempool
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"L2E-TX-{len(chain)}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "l2e_transfer",
        "from": from_thr,
        "to": to_thr,
        "thr_address": from_thr,
        "amount": round(amount, 6),
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "pending",
        "confirmation_policy": "FAST",
        "min_signers": 1,
    }
    pool = load_mempool()
    pool.append(tx)
    save_mempool(pool)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="pending", tx=tx, new_balance_from=ledger[from_thr]), 200

# ─── Courses API ───────────────────────────────────────────────────────
#
# These endpoints manage course creation, enrollment and completion for
# the Learn‑to‑Earn program.  Courses define a THR price and an L2E
# reward.  Students enroll by paying the THR cost (plus dynamic fee) to
# the instructor.  Upon completion, the instructor (or an admin)
# acknowledges the student's achievement and mints the L2E reward.

@app.route("/api/v1/courses", methods=["GET"])
def api_v1_get_courses():
    """Return the list of all courses."""
    courses = load_courses()
    return jsonify(courses=courses), 200


@app.route("/api/courses", methods=["GET"])
def api_courses_alias():
    """Alias for fetching courses without versioned prefix."""
    return api_v1_get_courses()


@app.route("/api/v1/courses/<string:course_id>", methods=["GET"])
def api_v1_get_course(course_id: str):
    """Return details of a specific course."""
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(error="course_not_found", course_id=course_id), 404
    return jsonify(course=course), 200


@app.route("/api/v1/courses", methods=["POST"])
def api_v1_create_course():
    """
    Create a new course with optional materials and quiz metadata. Supports
    both JSON payloads and multipart form submissions (for slide uploads).
    Required fields:
        - title: name of the course
        - teacher: THR address of the instructor
        - price_thr: cost in THR tokens to enroll
        - reward_l2e: number of L2E tokens to award upon completion
        - auth_secret & (optional) passphrase: authentication for teacher

    Optional metadata:
        - description/title_el
        - content_type: pdf | video | external
        - slides (file upload when content_type=pdf)
        - video_url / content_url
        - quiz: JSON structure containing pass_score and questions

    The teacher must be an existing pledged address with send rights. A new
    UUID is generated for the course ID. Materials are stored under
    ``media/courses/<course_id>``.
    """
    payload = request.get_json() if request.is_json else request.form.to_dict()
    data = payload or {}

    # Basic fields
    title = (data.get("title") or "").strip()
    teacher = (data.get("teacher") or "").strip()
    price_thr_raw = data.get("price_thr", 0)
    reward_raw = data.get("reward_l2e", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    description = (data.get("description") or "").strip()
    title_el = (data.get("title_el") or "").strip()

    # Validate basic fields
    try:
        price_thr = float(price_thr_raw)
        reward_l2e = float(reward_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid price or reward"), 400
    if not title or not teacher or price_thr < 0 or reward_l2e <= 0:
        return jsonify(status="error", message="Missing or invalid fields"), 400

    # Authenticate teacher
    pledges = load_json(PLEDGE_CHAIN, [])
    teacher_pledge = next((p for p in pledges if p.get("thr_address") == teacher), None)
    if not teacher_pledge:
        return jsonify(status="error", message="Teacher not found or has not pledged"), 404
    stored_auth_hash = teacher_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Teacher send not enabled"), 400
    if teacher_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403

    courses = load_courses()
    course_id = str(uuid.uuid4())

    # Handle materials (PDF/video/external)
    materials = {}
    content_type = (data.get("content_type") or "").strip().lower()
    if content_type in {"pdf", "video", "external"}:
        materials["type"] = content_type
        if content_type == "pdf":
            slides_file = request.files.get("slides") if not request.is_json else None
            if slides_file and slides_file.filename:
                _, ext = os.path.splitext(slides_file.filename)
                if ext.lower() != ".pdf":
                    return jsonify(status="error", message="Slides must be a PDF"), 400
                course_dir = os.path.join(MEDIA_DIR, "courses", course_id)
                os.makedirs(course_dir, exist_ok=True)
                slides_relative = os.path.join("courses", course_id, "slides.pdf")
                slides_file.save(os.path.join(MEDIA_DIR, slides_relative))
                materials["slides_path"] = slides_relative
            if "slides_path" not in materials:
                return jsonify(status="error", message="Slides PDF required for pdf content"), 400
        elif content_type == "video":
            materials["video_url"] = (data.get("video_url") or "").strip()
            if not materials["video_url"]:
                return jsonify(status="error", message="Video URL required for video content"), 400
        elif content_type == "external":
            materials["content_url"] = (data.get("content_url") or "").strip()
            if not materials["content_url"]:
                return jsonify(status="error", message="Content URL required for external content"), 400

    # Handle quiz metadata (builder payload from client)
    quiz_meta = None
    quiz_raw = data.get("quiz")
    if isinstance(quiz_raw, str):
        try:
            quiz_raw = json.loads(quiz_raw)
        except Exception:
            quiz_raw = None
    if isinstance(quiz_raw, dict):
        questions = []
        for idx, q in enumerate(quiz_raw.get("questions", []), start=1):
            opts = q.get("options", [])
            if len(opts) != 4:
                return jsonify(status="error", message=f"Question {idx} must have 4 options"), 400
            try:
                correct_idx = int(q.get("correct_index", 0))
            except Exception:
                correct_idx = 0
            questions.append({
                "id": q.get("id") or idx,
                "text": (q.get("text") or q.get("question") or "").strip(),
                "options": [str(o) for o in opts],
                "correct_index": max(0, min(3, correct_idx))
            })
        quiz_meta = {
            "pass_score": int(quiz_raw.get("pass_score", 70)),
            "questions": questions
        }

    new_course = {
        "id": course_id,
        "title": title,
        "title_el": title_el,
        "description": description,
        "teacher": teacher,
        "price_thr": round(price_thr, 6),
        "reward_l2e": round(reward_l2e, 6),
        "students": [],
        "completed": []
    }

    metadata = {}
    if materials:
        metadata["materials"] = materials
    if quiz_meta:
        metadata["quiz"] = quiz_meta
    if metadata:
        new_course["metadata"] = metadata

    courses.append(new_course)
    save_courses(courses)

    # Mirror quiz metadata into quizzes.json for backward compatibility
    if quiz_meta:
        quizzes = load_quizzes()
        quizzes[course_id] = {
            "course_id": course_id,
            "title": f"{title} Quiz",
            "title_el": f"{title} Quiz",
            "passing_score": quiz_meta.get("pass_score", 70),
            "questions": [
                {
                    "id": q.get("id") or i + 1,
                    "question": q.get("text"),
                    "options": q.get("options", []),
                    "correct": q.get("correct_index", 0)
                }
                for i, q in enumerate(quiz_meta.get("questions", []))
            ],
        }
        save_quizzes(quizzes)

    return jsonify(status="success", course=new_course), 201


@app.route("/api/v1/courses/<string:course_id>/enroll", methods=["POST"])
def api_v1_enroll_course(course_id: str):
    """
    Enroll a student in a course.  The payload must include:
        - student_thr: the enrolling student's THR address
        - auth_secret & optional passphrase: authentication for student

    The student's THR balance is debited by the course price plus burn fee,
    and the teacher's balance is credited by the price minus fee.  A
    ``course_payment`` transaction is added to the mempool.  The student
    is added to the course's ``students`` list.  Duplicate enrollments
    return a no‑op success.
    """
    data = request.get_json() or {}
    student = (data.get("student_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    if not student or not auth_secret:
        return jsonify(status="error", message="Missing student or auth_secret"), 400
    # Fetch the course
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(status="error", message="Course not found"), 404
    if student in course.get("students", []):
        return jsonify(status="success", message="Already enrolled"), 200
    # Validate student's pledge and auth
    pledges = load_json(PLEDGE_CHAIN, [])
    student_pledge = next((p for p in pledges if p.get("thr_address") == student), None)
    if not student_pledge:
        return jsonify(status="error", message="Student has not pledged"), 404
    stored_auth_hash = student_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Student send not enabled"), 400
    if student_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403
    # Determine cost and fee
    price = float(course.get("price_thr", 0.0))
    fee = calculate_dynamic_fee(price)
    total_cost = price + fee
    # Load THR ledger
    ledger = load_json(LEDGER_FILE, {})
    student_balance = float(ledger.get(student, 0.0))
    if student_balance < total_cost:
        return jsonify(
            status="error",
            message="Insufficient balance",
            balance=round(student_balance, 6),
            required=round(total_cost, 6)
        ), 400
    # Deduct from student and credit teacher
    ledger[student] = round(student_balance - total_cost, 6)
    teacher = course.get("teacher")
    ledger[teacher] = round(float(ledger.get(teacher, 0.0)) + price, 6)
    save_json(LEDGER_FILE, ledger)
    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"COURSE-PAY-{len(chain)}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "course_payment",
        "from": student,
        "to": teacher,
        "thr_address": student,
        "amount": round(price, 6),
        "fee_burned": fee,
        "course_id": course_id,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "pending",
        "confirmation_policy": "FAST",
        "min_signers": 1,
    }
    # Burn the fee by sending to the burn address (deducted in ledger)
    # Note: We do not credit the fee anywhere; it is effectively removed.
    pool = load_mempool()
    pool.append(tx)
    save_mempool(pool)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    # Enroll student
    course.setdefault("students", []).append(student)
    enrollments = load_enrollments()
    enrollments.setdefault(course_id, {})[student] = {
        "enrolled_at": ts,
        "completed": False
    }
    save_enrollments(enrollments)
    save_courses(courses)
    return jsonify(status="success", tx=tx, new_balance_from=ledger[student]), 200


@app.route("/api/courses/enroll", methods=["POST"])
def api_courses_enroll_alias():
    """Alias wrapper that forwards to the versioned enroll endpoint."""
    data = request.get_json() or {}
    course_id = (data.get("course_id") or data.get("id") or "").strip()
    if not course_id:
        return jsonify(status="error", message="Missing course_id"), 400
    return api_v1_enroll_course(course_id)


@app.route("/api/v1/courses/<string:course_id>/complete", methods=["POST"])
def api_v1_complete_course(course_id: str):
    """
    Mark a student's course as completed and award their L2E reward.  The
    payload must include:
        - student_thr: THR address of the student
        - teacher_thr: THR address of the instructor
        - auth_secret & optional passphrase: authentication for the teacher

    The function verifies the teacher is indeed the course creator and
    authenticates them.  The student must be enrolled and not already
    completed.  Upon success, the student's L2E balance is credited via
    internal minting (similar to /admin/mint_l2e) and a transaction of
    type ``l2e_reward`` is recorded.  The student is added to the
    ``completed`` list of the course.
    """
    data = request.get_json() or {}
    student = (data.get("student_thr") or "").strip()
    teacher = (data.get("teacher_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    if not student or not teacher or not auth_secret:
        return jsonify(status="error", message="Missing required fields"), 400
    # Fetch course
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(status="error", message="Course not found"), 404
    if course.get("teacher") != teacher:
        return jsonify(status="error", message="Teacher mismatch"), 403
    # Authenticate teacher
    pledges = load_json(PLEDGE_CHAIN, [])
    teacher_pledge = next((p for p in pledges if p.get("thr_address") == teacher), None)
    if not teacher_pledge:
        return jsonify(status="error", message="Teacher has not pledged"), 404
    stored_auth_hash = teacher_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Teacher send not enabled"), 400
    if teacher_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403
    # Check enrollment and completion status
    if student not in course.get("students", []):
        return jsonify(status="error", message="Student not enrolled"), 400
    if student in course.get("completed", []):
        return jsonify(status="success", message="Already completed"), 200
    # Determine reward
    reward = float(course.get("reward_l2e", 0.0))
    if reward <= 0:
        return jsonify(status="error", message="Invalid reward"), 500
    # Update L2E ledger
    l2e_ledger = load_json(L2E_LEDGER_FILE, {})
    l2e_ledger[student] = round(float(l2e_ledger.get(student, 0.0)) + reward, 6)
    save_json(L2E_LEDGER_FILE, l2e_ledger)
    # Record reward transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"L2E-REWARD-{len(chain)}-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "l2e_reward",
        "from": "course",
        "to": student,
        "thr_address": teacher,
        "amount": round(reward, 6),
        "course_id": course_id,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    # Mark as completed
    course.setdefault("completed", []).append(student)
    save_courses(courses)
    return jsonify(status="success", tx=tx), 200


# ─── Quiz API for Courses ──────────────────────────────────────────────
#
# Each course can have an optional quiz.  Quizzes are stored as a list of
# questions with multiple choice answers.  Students must pass the quiz
# (80% correct) before the teacher can mark them as complete.

QUIZZES_FILE = os.path.join(DATA_DIR, "quizzes.json")

def load_quizzes():
    return load_json(QUIZZES_FILE, {})

def save_quizzes(quizzes):
    save_json(QUIZZES_FILE, quizzes)


def get_course_quiz(course_id: str):
    """Return normalized quiz payload from course metadata or quizzes.json."""
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    metadata_quiz = course.get("metadata", {}).get("quiz") if course else None

    if metadata_quiz:
        normalized_questions = []
        for idx, q in enumerate(metadata_quiz.get("questions", []), start=1):
            options = q.get("options", [])
            normalized_questions.append({
                "id": q.get("id") or idx,
                "question": q.get("text") or q.get("question"),
                "options": options,
                "correct_index": int(q.get("correct_index", 0)),
            })
        return {
            "course_id": course_id,
            "title": metadata_quiz.get("title") or (course.get("title") if course else "Course") + " Quiz",
            "pass_score": metadata_quiz.get("pass_score", metadata_quiz.get("passing_score", 80)),
            "questions": normalized_questions,
        }

    quizzes = load_quizzes()
    quiz = quizzes.get(course_id)
    if quiz:
        normalized_questions = []
        for q in quiz.get("questions", []):
            normalized_questions.append({
                "id": q.get("id"),
                "question": q.get("question"),
                "options": q.get("options", []),
                "correct_index": int(q.get("correct", 0)),
            })
        return {
            "course_id": course_id,
            "title": quiz.get("title", "Course Quiz"),
            "pass_score": quiz.get("passing_score", 80),
            "questions": normalized_questions,
        }
    return None


@app.route("/api/v1/courses/<string:course_id>/quiz", methods=["GET"])
def api_v1_get_quiz(course_id: str):
    """Return the quiz for a course (without correct answers for students)."""
    quiz = get_course_quiz(course_id)
    if not quiz:
        return jsonify(quiz=None, message="No quiz for this course"), 200

    safe_questions = []
    for q in quiz.get("questions", []):
        safe_questions.append({
            "id": q.get("id"),
            "question": q.get("question"),
            "options": q.get("options", [])
        })

    return jsonify(quiz={
        "course_id": course_id,
        "title": quiz.get("title", "Course Quiz"),
        "passing_score": quiz.get("pass_score", 80),
        "questions": safe_questions
    }), 200


@app.route("/api/v1/courses/<string:course_id>/quiz", methods=["POST"])
def api_v1_create_quiz(course_id: str):
    """Create or update a quiz for a course. Teacher only."""
    data = request.get_json() or {}
    teacher = (data.get("teacher_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    questions = data.get("questions", [])

    if not teacher or not auth_secret:
        return jsonify(status="error", message="Missing auth"), 400

    # Verify course exists and teacher owns it
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(status="error", message="Course not found"), 404
    if course.get("teacher") != teacher:
        return jsonify(status="error", message="Not the course teacher"), 403

    # Authenticate teacher
    pledges = load_json(PLEDGE_CHAIN, [])
    teacher_pledge = next((p for p in pledges if p.get("thr_address") == teacher), None)
    if not teacher_pledge:
        return jsonify(status="error", message="Teacher not pledged"), 404
    stored_auth_hash = teacher_pledge.get("send_auth_hash")
    if teacher_pledge.get("has_passphrase"):
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403

    # Validate questions format
    validated_questions = []
    for i, q in enumerate(questions):
        if not q.get("question") or not q.get("options") or q.get("correct") is None:
            return jsonify(status="error", message=f"Invalid question #{i+1}"), 400
        validated_questions.append({
            "id": i + 1,
            "question": q.get("question"),
            "question_el": q.get("question_el", q.get("question")),
            "options": q.get("options"),
            "options_el": q.get("options_el", q.get("options")),
            "correct": int(q.get("correct"))
        })

    # FIX B1: Save quiz with quiz_id and updated_at for cache busting
    import uuid
    quizzes = load_quizzes()
    existing_quiz = quizzes.get(course_id, {})
    quiz_id = existing_quiz.get("quiz_id", str(uuid.uuid4()))

    quizzes[course_id] = {
        "quiz_id": quiz_id,
        "course_id": course_id,
        "title": data.get("title", "Course Quiz"),
        "title_el": data.get("title_el", "Quiz Μαθήματος"),
        "passing_score": int(data.get("passing_score", 80)),
        "questions": validated_questions,
        "created_at": existing_quiz.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "version": existing_quiz.get("version", 0) + 1
    }
    save_quizzes(quizzes)

    app.logger.info(f"Quiz saved for course {course_id}: {len(validated_questions)} questions, version {quizzes[course_id]['version']}")

    return jsonify(status="success", message="Quiz saved"), 201


@app.route("/api/v1/courses/<string:course_id>/quiz/submit", methods=["POST"])
def api_v1_submit_quiz(course_id: str):
    """Submit quiz answers and get score. Records passing status."""
    data = request.get_json() or {}
    student = (data.get("student_thr") or "").strip()
    answers = data.get("answers", {})

    if not student:
        return jsonify(status="error", message="Student address required"), 400

    # Get quiz
    quiz = get_course_quiz(course_id)
    if not quiz:
        return jsonify(status="error", message="No quiz for this course"), 404

    # Check enrollment
    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(status="error", message="Course not found"), 404
    if student not in course.get("students", []):
        return jsonify(status="error", message="Not enrolled"), 403

    # Calculate score
    questions = quiz.get("questions", [])
    total = len(questions)
    if total == 0:
        return jsonify(status="error", message="Quiz has no questions"), 500

    correct = 0
    results = []
    for q in questions:
        qid = str(q.get("id"))
        user_answer = answers.get(qid)
        is_correct = user_answer is not None and int(user_answer) == q.get("correct_index")
        if is_correct:
            correct += 1
        results.append({
            "question_id": qid,
            "correct": is_correct,
            "your_answer": user_answer,
            "correct_answer": q.get("correct_index")
        })

    score = round((correct / total) * 100)
    passing_score = quiz.get("pass_score", 80)
    passed = score >= passing_score

    # Record quiz attempt
    quiz_attempts = load_json(os.path.join(DATA_DIR, "quiz_attempts.json"), {})
    if course_id not in quiz_attempts:
        quiz_attempts[course_id] = {}
    quiz_attempts[course_id][student] = {
        "score": score,
        "passed": passed,
        "attempts": quiz_attempts.get(course_id, {}).get(student, {}).get("attempts", 0) + 1,
        "last_attempt": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    save_json(os.path.join(DATA_DIR, "quiz_attempts.json"), quiz_attempts)

    # Mark as quiz_passed in course if passed
    if passed:
        if "quiz_passed" not in course:
            course["quiz_passed"] = []
        if student not in course["quiz_passed"]:
            course["quiz_passed"].append(student)
            save_courses(courses)

    return jsonify(
        status="success",
        score=score,
        correct=correct,
        total=total,
        passed=passed,
        passing_score=passing_score,
        results=results
    ), 200


@app.route("/api/l2e/submit_quiz", methods=["POST"])
def api_l2e_submit_quiz():
    """Grade a quiz attempt, record completion, and award L2E tokens."""
    data = request.get_json() or {}
    course_id = (data.get("course_id") or data.get("id") or "").strip()
    student = (data.get("student_thr") or "").strip()
    answers = data.get("answers", {})

    if not course_id or not student:
        return jsonify(status="error", message="Missing course or student"), 400

    courses = load_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return jsonify(status="error", message="Course not found"), 404

    enrollments = load_enrollments()
    if student not in enrollments.get(course_id, {}) and student not in course.get("students", []):
        return jsonify(status="error", message="Not enrolled"), 403

    quiz = get_course_quiz(course_id)
    if not quiz:
        return jsonify(status="error", message="No quiz for this course"), 404

    questions = quiz.get("questions", [])
    total = len(questions)
    if total == 0:
        return jsonify(status="error", message="Quiz has no questions"), 500

    correct = 0
    results = []
    for q in questions:
        qid = str(q.get("id"))
        user_answer = answers.get(qid)
        is_correct = user_answer is not None and int(user_answer) == q.get("correct_index")
        if is_correct:
            correct += 1
        results.append({
            "question_id": qid,
            "correct": is_correct,
            "your_answer": user_answer,
            "correct_answer": q.get("correct_index")
        })

    score = round((correct / total) * 100)
    passing_score = quiz.get("pass_score", 80)
    passed = score >= passing_score

    quiz_attempts = load_json(os.path.join(DATA_DIR, "quiz_attempts.json"), {})
    if course_id not in quiz_attempts:
        quiz_attempts[course_id] = {}
    quiz_attempts[course_id][student] = {
        "score": score,
        "passed": passed,
        "attempts": quiz_attempts.get(course_id, {}).get(student, {}).get("attempts", 0) + 1,
        "last_attempt": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    save_json(os.path.join(DATA_DIR, "quiz_attempts.json"), quiz_attempts)

    # FIX B2: AUTO-COMPLETE + AUTO-REWARD
    auto_completed = False
    reward_credited = False
    reward_amount = 0.0

    if passed:
        # Mark course completed in enrollments
        enrollments.setdefault(course_id, {}).setdefault(student, {})["completed"] = True
        enrollments[course_id][student]["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        save_enrollments(enrollments)

        # Mark in course object
        course.setdefault("completed", [])
        if student not in course["completed"]:
            course["completed"].append(student)
            save_courses(courses)

        auto_completed = True
        app.logger.info(f"AUTO-COMPLETE: Student {student} completed course {course_id}")

        # AUTO-REWARD: Credit L2E reward
        reward_amount = float(course.get("metadata", {}).get("reward_thr", 0.0) or course.get("reward_l2e", 0.0))
        if reward_amount > 0:
            # Credit to main wallet ledger
            ledger = load_json(LEDGER_FILE, {})
            ledger[student] = round(float(ledger.get(student, 0.0)) + reward_amount, 6)
            save_json(LEDGER_FILE, ledger)

            # Also credit to L2E ledger for tracking
            l2e_ledger = load_json(L2E_LEDGER_FILE, {})
            l2e_ledger[student] = round(float(l2e_ledger.get(student, 0.0)) + reward_amount, 6)
            save_json(L2E_LEDGER_FILE, l2e_ledger)

            # Write transaction entry to wallet history
            chain = load_json(CHAIN_FILE, [])
            reward_tx = {
                "tx_id": f"L2E_{course_id}_{int(time.time())}",
                "type": "L2E_REWARD",
                "from": "SYSTEM_L2E_POOL",
                "to": student,
                "amount": reward_amount,
                "course_id": course_id,
                "quiz_score": score,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "block": len(chain) + 1
            }
            chain.append(reward_tx)
            save_json(CHAIN_FILE, chain)

            reward_credited = True
            app.logger.info(f"AUTO-REWARD: Credited {reward_amount} THR to {student} for completing {course_id}")
            chain = load_json(CHAIN_FILE, [])
            ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            tx_id = f"L2E-REWARD-{len(chain)}-{int(time.time())}-{secrets.token_hex(4)}"
            chain.append({
                "type": "l2e_reward",
                "from": "course",
                "to": student,
                "thr_address": course.get("teacher", ""),
                "amount": round(reward, 6),
                "course_id": course_id,
                "timestamp": ts,
                "tx_id": tx_id,
                "status": "confirmed"
            })
            save_json(CHAIN_FILE, chain)
            update_last_block(chain[-1], is_block=False)
        save_enrollments(enrollments)
        save_courses(courses)

    return jsonify(
        status="success",
        score=score,
        total=total,
        correct=correct,
        passed=passed,
        passing_score=passing_score,
        results=results,
        message=f"Quiz graded. Score: {score}% ({correct}/{total})" + (" - PASSED!" if passed else ""),
        auto_completed=auto_completed,
        reward_credited=reward_credited,
        reward_amount=reward_amount
    ), 200


@app.route("/api/courses/quiz/submit", methods=["POST"])
def api_courses_quiz_submit_alias():
    """Alias wrapper for submitting course quizzes without the v1 prefix."""
    data = request.get_json() or {}
    course_id = (data.get("course_id") or data.get("id") or "").strip()
    if not course_id:
        return jsonify(status="error", message="Missing course_id"), 400
    return api_v1_submit_quiz(course_id)


@app.route("/api/v1/courses/<string:course_id>/quiz/status/<string:student>", methods=["GET"])
def api_v1_quiz_status(course_id: str, student: str):
    """Check if a student has passed the quiz."""
    quiz_attempts = load_json(os.path.join(DATA_DIR, "quiz_attempts.json"), {})
    attempt = quiz_attempts.get(course_id, {}).get(student, {})

    return jsonify(
        has_attempted=bool(attempt),
        passed=attempt.get("passed", False),
        score=attempt.get("score", 0),
        attempts=attempt.get("attempts", 0)
    ), 200


# ─── Tokens & Pools API ───────────────────────────────────────────────
#
# These endpoints implement a minimal DeFi layer for community‑issued
# tokens and liquidity pools.  They are experimental and subject to
# change in future releases.

@app.route("/api/v1/tokens", methods=["GET"])
def api_v1_get_tokens():
    """
    List all issued tokens.  Each token entry includes its symbol,
    name, total supply, decimals and owner.
    """
    wallet = (request.args.get("wallet") or "").strip() or None
    tokens = get_all_tokens()

    if wallet:
        balances = get_wallet_balances(wallet)
        token_map = {t.get("symbol"): t for t in tokens}
        for t in balances.get("tokens", []):
            sym = t.get("symbol")
            if not sym:
                continue
            entry = token_map.setdefault(sym, {})
            entry.update({k: v for k, v in t.items() if k not in entry})

    return jsonify(tokens=tokens), 200


@app.route("/api/v1/tokens", methods=["POST"])
def api_v1_create_token():
    """
    Create a new fungible token (meme coin).  Payload must include:
      - name: human‑readable token name
      - symbol: uppercase symbol (1‑8 chars), unique among tokens and distinct from THR
      - total_supply: positive number of units to mint
      - decimals: number of decimal places (0‑18)
      - creator_thr: THR address of the token issuer
      - auth_secret & optional passphrase: for authenticating the creator

    On success, the token is recorded in ``tokens.json`` and the entire
    supply is assigned to the creator in ``token_balances.json``.  A
    ``token_create`` transaction is appended to the chain for auditability.
    """
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    symbol = (data.get("symbol") or "").strip().upper()
    total_raw = data.get("total_supply", 0)
    decimals = data.get("decimals", 0)
    creator = (data.get("creator_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    # Validate inputs
    try:
        total_supply = float(total_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid total_supply"), 400
    if not name or not symbol or total_supply <= 0:
        return jsonify(status="error", message="Missing or invalid fields"), 400
    if not creator or not auth_secret:
        return jsonify(status="error", message="Missing creator or auth_secret"), 400
    if len(symbol) > 8 or not symbol.isalnum():
        return jsonify(status="error", message="Symbol must be 1‑8 alphanumeric chars"), 400
    if symbol in ("THR", "WBTC"):
        return jsonify(status="error", message="Symbol reserved"), 400
    try:
        decimals_int = int(decimals)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid decimals"), 400
    if decimals_int < 0 or decimals_int > 18:
        return jsonify(status="error", message="Decimals out of range (0‑18)"), 400
    # Check uniqueness
    tokens = load_tokens()
    if any(t.get("symbol") == symbol for t in tokens):
        return jsonify(status="error", message="Token symbol already exists"), 400
    # Authenticate creator via pledge send auth
    pledges = load_json(PLEDGE_CHAIN, [])
    creator_pledge = next((p for p in pledges if p.get("thr_address") == creator), None)
    if not creator_pledge:
        return jsonify(status="error", message="Creator has not pledged"), 404
    stored_auth_hash = creator_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Creator send not enabled"), 400
    if creator_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403
    # Create token
    token_id = str(uuid.uuid4())
    new_token = {
        "id": token_id,
        "name": name,
        "symbol": symbol,
        "total_supply": round(total_supply, decimals_int),
        "decimals": decimals_int,
        "owner": creator
    }
    tokens.append(new_token)
    save_tokens(tokens)
    # Update token balances
    balances = load_token_balances()
    if symbol not in balances:
        balances[symbol] = {}
    balances[symbol][creator] = round(total_supply, decimals_int)
    save_token_balances(balances)
    # Record transaction in chain
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"TOKEN-CREATE-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "token_create",
        "symbol": symbol,
        "name": name,
        "decimals": decimals_int,
        "owner": creator,
        "total_supply": round(total_supply, decimals_int),
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="success", token=new_token), 201


@app.route("/api/v1/pools", methods=["GET"])
def api_v1_get_pools():
    """Return the list of all liquidity pools."""
    pools = load_pools()
    return jsonify(pools=pools), 200


@app.route("/api/v1/pools/positions/<address>")
def api_v1_user_positions(address):
    """
    Get user's liquidity positions with calculated values.
    Returns share amounts, token amounts, and estimated values.
    """
    if not address or not validate_thr_address(address):
        return jsonify(status="error", message="Invalid address"), 400

    pools = load_pools()
    user_positions = []

    # Get THR price for value calculations
    thr_price = 0.0042  # Default, could be from external source

    for pool in pools:
        providers = pool.get("providers", {})
        user_shares = float(providers.get(address, 0))

        if user_shares > 0:
            total_shares = float(pool.get("total_shares", 0))
            reserves_a = float(pool.get("reserves_a", 0))
            reserves_b = float(pool.get("reserves_b", 0))

            # Calculate user's portion of each token
            share_ratio = user_shares / total_shares if total_shares > 0 else 0
            token_a_amount = round(reserves_a * share_ratio, 6)
            token_b_amount = round(reserves_b * share_ratio, 6)

            # Estimate value in THR
            token_a = pool.get("token_a", "")
            token_b = pool.get("token_b", "")

            # Simple value estimation (in THR)
            value_thr = 0
            if token_a == "THR":
                value_thr += token_a_amount
            elif token_a == "WBTC":
                value_thr += token_a_amount * 8000000  # ~8M THR per WBTC estimate
            else:
                value_thr += token_a_amount * 0.01  # Custom tokens rough estimate

            if token_b == "THR":
                value_thr += token_b_amount
            elif token_b == "WBTC":
                value_thr += token_b_amount * 8000000
            else:
                value_thr += token_b_amount * 0.01

            position = {
                "pool_id": pool.get("id"),
                "token_a": token_a,
                "token_b": token_b,
                "user_shares": round(user_shares, 6),
                "total_shares": round(total_shares, 6),
                "share_percent": round(share_ratio * 100, 4),
                "token_a_amount": token_a_amount,
                "token_b_amount": token_b_amount,
                "value_thr": round(value_thr, 6),
                "value_usd": round(value_thr * thr_price, 2),
                "reserves_a": reserves_a,
                "reserves_b": reserves_b
            }

            # Add referral info if available
            referrals = pool.get("referrals", {})
            user_referrals = [addr for addr, ref in referrals.items() if ref == address]
            if user_referrals:
                position["referral_count"] = len(user_referrals)
                position["referral_bonus_earned"] = round(len(user_referrals) * 0.001, 6)  # 0.1% bonus per referral

            user_positions.append(position)

    # Calculate totals
    total_value_thr = sum(p["value_thr"] for p in user_positions)
    total_value_usd = sum(p["value_usd"] for p in user_positions)

    return jsonify({
        "status": "success",
        "address": address,
        "positions": user_positions,
        "total_pools": len(user_positions),
        "total_value_thr": round(total_value_thr, 6),
        "total_value_usd": round(total_value_usd, 2)
    }), 200


@app.route("/api/v1/pools/referral/<pool_id>")
def api_v1_pool_referral_stats(pool_id):
    """Get referral statistics for a pool."""
    pools = load_pools()
    pool = next((p for p in pools if p.get("id") == pool_id), None)

    if not pool:
        return jsonify(status="error", message="Pool not found"), 404

    referrals = pool.get("referrals", {})

    # Group referrals by referrer
    referrer_stats = {}
    for referred, referrer in referrals.items():
        if referrer not in referrer_stats:
            referrer_stats[referrer] = []
        referrer_stats[referrer].append(referred)

    return jsonify({
        "status": "success",
        "pool_id": pool_id,
        "total_referrals": len(referrals),
        "referrer_stats": {k: len(v) for k, v in referrer_stats.items()}
    }), 200


@app.route("/api/v1/pools", methods=["POST"])
def api_v1_create_pool():
    """
    Create a new liquidity pool for a pair of tokens.  Payload must include:
      - token_a: symbol of first token (e.g. THR, WBTC or custom token)
      - token_b: symbol of second token (must differ from token_a)
      - amount_a: amount of token_a to deposit
      - amount_b: amount of token_b to deposit
      - provider_thr: THR address providing liquidity
      - auth_secret & optional passphrase: authentication for provider

    The provider must have sufficient balances for both tokens.  Native
    tokens THR and WBTC are debited from their respective ledgers; custom
    tokens are debited from the same custom token ledgers used by the
    wallet widget.  A new pool entry is created with reserves and a
    simple share model (shares equal to the geometric mean of the
    deposits).  No trading fee logic is applied yet.
    """
    data = request.get_json() or {}
    token_a = (data.get("token_a") or "").upper().strip()
    token_b = (data.get("token_b") or "").upper().strip()
    amt_a_raw = data.get("amount_a", 0)
    amt_b_raw = data.get("amount_b", 0)
    provider = (data.get("provider_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    # Basic validation
    try:
        amt_a = Decimal(str(amt_a_raw))
        amt_b = Decimal(str(amt_b_raw))
    except Exception:
        return jsonify(status="error", message="Invalid amounts"), 400
    if not token_a or not token_b or token_a == token_b:
        return jsonify(status="error", message="Token symbols must be distinct"), 400
    if amt_a <= 0 or amt_b <= 0:
        return jsonify(status="error", message="Amounts must be positive"), 400
    if not provider or not auth_secret:
        return jsonify(status="error", message="Missing provider or auth_secret"), 400
    # Validate provider send rights
    pledges = load_json(PLEDGE_CHAIN, [])
    provider_pledge = next((p for p in pledges if p.get("thr_address") == provider), None)
    if not provider_pledge:
        return jsonify(status="error", message="Provider has not pledged"), 404
    stored_auth_hash = provider_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Provider send not enabled"), 400
    if provider_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403
    wallet_snapshot = get_wallet_balances(provider)
    tokens_by_symbol = {t.get("symbol"): t for t in wallet_snapshot.get("tokens", [])}

    thr_ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    l2e_ledger = load_json(L2E_LEDGER_FILE, {})
    custom_tokens = load_custom_tokens()

    def resolve_token_state(sym: str):
        if sym == "THR":
            return {
                "symbol": sym,
                "decimals": 6,
                "ledger": thr_ledger,
                "balance": Decimal(str(wallet_snapshot.get("thr", 0.0))),
                "save": lambda: save_json(LEDGER_FILE, thr_ledger)
            }
        if sym == "WBTC":
            return {
                "symbol": sym,
                "decimals": 8,
                "ledger": wbtc_ledger,
                "balance": Decimal(str(wallet_snapshot.get("wbtc", 0.0))),
                "save": lambda: save_json(WBTC_LEDGER_FILE, wbtc_ledger)
            }
        if sym == "L2E":
            return {
                "symbol": sym,
                "decimals": 6,
                "ledger": l2e_ledger,
                "balance": Decimal(str(wallet_snapshot.get("l2e", 0.0))),
                "save": lambda: save_json(L2E_LEDGER_FILE, l2e_ledger)
            }
        token_meta = custom_tokens.get(sym)
        if not token_meta:
            return None
        token_id = token_meta.get("id")
        if not token_id:
            return None
        token_ledger = load_custom_token_ledger(token_id)
        decimals = int(token_meta.get("decimals", 6))
        return {
            "symbol": sym,
            "decimals": decimals,
            "ledger": token_ledger,
            "token_id": token_id,
            "balance": Decimal(str(token_ledger.get(provider, 0.0))),
            "save": lambda ledger=token_ledger, token_id=token_id: save_custom_token_ledger(token_id, ledger)
        }

    def to_units(amount: Decimal, decimals: int):
        scale = Decimal(10) ** decimals
        return int((amount * scale).to_integral_value(rounding=ROUND_DOWN))

    def validate_and_prepare(sym: str, amt: Decimal):
        state = resolve_token_state(sym)
        if not state:
            return None, jsonify(status="error", message=f"Unsupported token {sym}"), 400
        amount_units = to_units(amt, state["decimals"])
        balance_units = to_units(state["balance"], state["decimals"])
        if amount_units <= 0:
            return None, jsonify(status="error", message="Amounts must be positive"), 400
        if balance_units < amount_units:
            return None, jsonify(status="error", message="Insufficient balance for one of the tokens", requested={"symbol": sym, "amount": float(amt)}, available=float(state["balance"])), 400
        return state, None, None

    state_a, err_resp_a, err_code_a = validate_and_prepare(token_a, amt_a)
    if err_resp_a:
        return err_resp_a, err_code_a
    state_b, err_resp_b, err_code_b = validate_and_prepare(token_b, amt_b)
    if err_resp_b:
        return err_resp_b, err_code_b

    logger.info("[create_pool] provider=%s token_a=%s amount_a=%s token_b=%s amount_b=%s balances=%s", provider, token_a, amt_a, token_b, amt_b, {k: {"balance": v.get("balance"), "decimals": v.get("decimals") } for k, v in tokens_by_symbol.items()})

    amt_a_quantized = amt_a.quantize(Decimal(1) / (Decimal(10) ** state_a["decimals"]), rounding=ROUND_DOWN)
    amt_b_quantized = amt_b.quantize(Decimal(1) / (Decimal(10) ** state_b["decimals"]), rounding=ROUND_DOWN)

    def deduct(state, amt: Decimal):
        decimals = state["decimals"]
        ledger = state["ledger"]
        current = Decimal(str(ledger.get(provider, 0.0)))
        new_balance = (current - amt).quantize(Decimal(1) / (Decimal(10) ** decimals), rounding=ROUND_DOWN)
        ledger[provider] = float(new_balance)
        state["save"]()

    deduct(state_a, amt_a_quantized)
    deduct(state_b, amt_b_quantized)
    # Create pool
    pools = load_pools()
    # Ensure pool doesn't already exist
    for p in pools:
        if (p.get("token_a") == token_a and p.get("token_b") == token_b) or (p.get("token_a") == token_b and p.get("token_b") == token_a):
            return jsonify(status="error", message="Pool already exists"), 400
    pool_id = str(uuid.uuid4())
    amt_a_float = float(amt_a_quantized)
    amt_b_float = float(amt_b_quantized)
    # Compute shares as geometric mean (simplified constant product)
    try:
        shares = (amt_a_float * amt_b_float) ** 0.5
    except Exception:
        shares = min(amt_a_float, amt_b_float)
    new_pool = {
        "id": pool_id,
        "token_a": token_a,
        "token_b": token_b,
        "reserves_a": round(amt_a_float, state_a["decimals"]),
        "reserves_b": round(amt_b_float, state_b["decimals"]),
        "total_shares": round(shares, 6),
        "providers": {
            provider: round(shares, 6)
        }
    }
    pools.append(new_pool)
    save_pools(pools)
    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"POOL-CREATE-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "pool_create",
        "pool_id": pool_id,
        "token_a": token_a,
        "token_b": token_b,
        "deposited_a": round(amt_a_float, state_a["decimals"]),
        "deposited_b": round(amt_b_float, state_b["decimals"]),
        "provider": provider,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    try:
        broadcast_tx(tx)
    except Exception:
        pass
    return jsonify(status="success", pool=new_pool), 201


# ─── ADD LIQUIDITY TO EXISTING POOL ────────────────────────────────────
@app.route("/api/v1/pools/add_liquidity", methods=["POST"])
def api_v1_add_liquidity():
    """
    Add liquidity to an existing pool. Shares are minted proportionally.

    Request body:
    {
        "pool_id": "uuid...",
        "amount_a": 100.0,
        "amount_b": 0.01,
        "provider_thr": "THR...",
        "auth_secret": "...",
        "passphrase": "..."
    }
    """
    data = request.get_json() or {}
    pool_id = (data.get("pool_id") or "").strip()
    amt_a_raw = data.get("amount_a", 0)
    amt_b_raw = data.get("amount_b", 0)
    provider = (data.get("provider_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()
    referrer = (data.get("referrer") or "").strip()  # Optional referral address

    # Validate inputs
    try:
        amt_a = float(amt_a_raw)
        amt_b = float(amt_b_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid amounts"), 400

    if not pool_id or amt_a <= 0 or amt_b <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    if not provider or not auth_secret:
        return jsonify(status="error", message="Missing provider or auth_secret"), 400

    # Authenticate
    pledges = load_json(PLEDGE_CHAIN, [])
    provider_pledge = next((p for p in pledges if p.get("thr_address") == provider), None)
    if not provider_pledge:
        return jsonify(status="error", message="Provider has not pledged"), 404

    stored_auth_hash = provider_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Provider send not enabled"), 400

    if provider_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403

    # Load pool
    pools = load_pools()
    pool = next((p for p in pools if p.get("id") == pool_id), None)
    if not pool:
        return jsonify(status="error", message="Pool not found"), 404

    token_a = pool["token_a"]
    token_b = pool["token_b"]
    reserves_a = float(pool["reserves_a"])
    reserves_b = float(pool["reserves_b"])
    total_shares = float(pool["total_shares"])

    # Check if amounts maintain the ratio (allow small slippage)
    expected_ratio = reserves_a / reserves_b if reserves_b > 0 else 0
    provided_ratio = amt_a / amt_b if amt_b > 0 else 0

    if abs(expected_ratio - provided_ratio) / max(expected_ratio, 0.0001) > 0.02:  # 2% slippage tolerance
        return jsonify(
            status="error",
            message="Amounts don't match pool ratio",
            expected_ratio=expected_ratio,
            provided_ratio=provided_ratio
        ), 400

    # Check balances
    thr_ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    l2e_ledger = load_json(L2E_LEDGER_FILE, {})
    token_balances = load_token_balances()

    def available_balance(sym):
        if sym == "THR":
            return float(thr_ledger.get(provider, 0.0))
        if sym == "WBTC":
            return float(wbtc_ledger.get(provider, 0.0))
        if sym == "L2E":
            return float(l2e_ledger.get(provider, 0.0))

        custom_ledger = load_custom_token_ledger_by_symbol(sym) or {}
        ledger_balance = float(custom_ledger.get(provider, 0.0))
        token_balance = float(token_balances.get(sym, {}).get(provider, 0.0))
        return ledger_balance + token_balance

    available_a = available_balance(token_a)
    available_b = available_balance(token_b)

    if available_a < amt_a or available_b < amt_b:
        failing_token = token_a if available_a < amt_a else token_b
        required_amt = amt_a if available_a < amt_a else amt_b
        available_amt = available_a if available_a < amt_a else available_b
        logger.warning(
            "[add_liquidity][insufficient] provider=%s token=%s required=%s available=%s",
            provider,
            failing_token,
            required_amt,
            available_amt,
        )
        return jsonify(status="error", message="Insufficient balance"), 400

    # Deduct balances
    def deduct(sym, amt):
        if sym == "THR":
            thr_ledger[provider] = round(float(thr_ledger.get(provider, 0.0)) - amt, 6)
        elif sym == "WBTC":
            wbtc_ledger[provider] = round(float(wbtc_ledger.get(provider, 0.0)) - amt, 6)
        elif sym == "L2E":
            l2e_ledger[provider] = round(float(l2e_ledger.get(provider, 0.0)) - amt, 6)
        else:
            custom_ledger = load_custom_token_ledger_by_symbol(sym) or {}
            ledger_balance = float(custom_ledger.get(provider, 0.0))
            deduct_from_ledger = min(ledger_balance, amt)
            remaining = amt - deduct_from_ledger
            custom_ledger[provider] = round(ledger_balance - deduct_from_ledger, 6)
            save_custom_token_ledger_by_symbol(sym, custom_ledger)

            if remaining > 0:
                token_balances.setdefault(sym, {})
                token_balances[sym][provider] = round(float(token_balances[sym].get(provider, 0.0)) - remaining, 6)

    deduct(token_a, amt_a)
    deduct(token_b, amt_b)

    save_json(LEDGER_FILE, thr_ledger)
    save_json(WBTC_LEDGER_FILE, wbtc_ledger)
    save_json(L2E_LEDGER_FILE, l2e_ledger)
    save_token_balances(token_balances)

    # Mint shares proportional to liquidity added
    # shares_minted = min(amt_a / reserves_a, amt_b / reserves_b) * total_shares
    shares_minted = (amt_a / reserves_a) * total_shares if reserves_a > 0 else (amt_a * amt_b) ** 0.5

    # Update pool
    pool["reserves_a"] = round(reserves_a + amt_a, 6)
    pool["reserves_b"] = round(reserves_b + amt_b, 6)
    pool["total_shares"] = round(total_shares + shares_minted, 6)

    if "providers" not in pool:
        pool["providers"] = {}
    pool["providers"][provider] = round(float(pool["providers"].get(provider, 0.0)) + shares_minted, 6)

    # Track referral if provided and valid
    referral_bonus = 0
    if referrer and validate_thr_address(referrer) and referrer != provider:
        if "referrals" not in pool:
            pool["referrals"] = {}
        # Only track if this is first time adding liquidity (new provider)
        if provider not in pool["referrals"]:
            pool["referrals"][provider] = referrer
            # Give referrer bonus shares (0.5% of new shares)
            referral_bonus = round(shares_minted * 0.005, 6)
            pool["providers"][referrer] = round(float(pool["providers"].get(referrer, 0.0)) + referral_bonus, 6)
            pool["total_shares"] = round(float(pool["total_shares"]) + referral_bonus, 6)
            logger.info(f"Referral bonus: {referral_bonus} shares to {referrer} for referring {provider}")

    save_pools(pools)

    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"POOL-ADD-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "pool_add_liquidity",
        "pool_id": pool_id,
        "token_a": token_a,
        "token_b": token_b,
        "added_a": amt_a,
        "added_b": amt_b,
        "shares_minted": shares_minted,
        "provider": provider,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)

    try:
        broadcast_tx(tx)
    except Exception:
        pass

    response = {
        "status": "success",
        "shares_minted": shares_minted,
        "total_shares": pool["total_shares"],
        "provider_shares": pool["providers"][provider]
    }

    if referral_bonus > 0:
        response["referral_bonus"] = referral_bonus
        response["referrer"] = referrer

    return jsonify(response), 200


# ─── REMOVE LIQUIDITY FROM POOL ────────────────────────────────────
@app.route("/api/v1/pools/remove_liquidity", methods=["POST"])
def api_v1_remove_liquidity():
    """
    Remove liquidity from a pool by burning shares.

    Request body:
    {
        "pool_id": "uuid...",
        "shares": 10.0,
        "provider_thr": "THR...",
        "auth_secret": "...",
        "passphrase": "..."
    }
    """
    data = request.get_json() or {}
    pool_id = (data.get("pool_id") or "").strip()
    shares_raw = data.get("shares", 0)
    provider = (data.get("provider_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    try:
        shares = float(shares_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid shares amount"), 400

    if not pool_id or shares <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    if not provider or not auth_secret:
        return jsonify(status="error", message="Missing provider or auth_secret"), 400

    # Authenticate
    pledges = load_json(PLEDGE_CHAIN, [])
    provider_pledge = next((p for p in pledges if p.get("thr_address") == provider), None)
    if not provider_pledge:
        return jsonify(status="error", message="Provider has not pledged"), 404

    stored_auth_hash = provider_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Provider send not enabled"), 400

    if provider_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403

    # Load pool
    pools = load_pools()
    pool = next((p for p in pools if p.get("id") == pool_id), None)
    if not pool:
        return jsonify(status="error", message="Pool not found"), 404

    # Check provider has enough shares
    provider_shares = float(pool.get("providers", {}).get(provider, 0.0))
    if provider_shares < shares:
        return jsonify(
            status="error",
            message="Insufficient shares",
            your_shares=provider_shares,
            requested=shares
        ), 400

    token_a = pool["token_a"]
    token_b = pool["token_b"]
    reserves_a = float(pool["reserves_a"])
    reserves_b = float(pool["reserves_b"])
    total_shares = float(pool["total_shares"])

    # Calculate tokens to return
    share_fraction = shares / total_shares
    amt_a_return = reserves_a * share_fraction
    amt_b_return = reserves_b * share_fraction

    # Update pool
    pool["reserves_a"] = round(reserves_a - amt_a_return, 6)
    pool["reserves_b"] = round(reserves_b - amt_b_return, 6)
    pool["total_shares"] = round(total_shares - shares, 6)
    pool["providers"][provider] = round(provider_shares - shares, 6)

    # Remove provider if shares = 0
    if pool["providers"][provider] <= 0:
        del pool["providers"][provider]

    save_pools(pools)

    # Credit tokens back to provider
    thr_ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    token_balances = load_token_balances()

    def credit(sym, amt):
        if sym == "THR":
            thr_ledger[provider] = round(float(thr_ledger.get(provider, 0.0)) + amt, 6)
        elif sym == "WBTC":
            wbtc_ledger[provider] = round(float(wbtc_ledger.get(provider, 0.0)) + amt, 6)
        else:
            token_balances.setdefault(sym, {})
            token_balances[sym][provider] = round(float(token_balances[sym].get(provider, 0.0)) + amt, 6)

    credit(token_a, amt_a_return)
    credit(token_b, amt_b_return)

    save_json(LEDGER_FILE, thr_ledger)
    save_json(WBTC_LEDGER_FILE, wbtc_ledger)
    save_token_balances(token_balances)

    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"POOL-REMOVE-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "pool_remove_liquidity",
        "pool_id": pool_id,
        "token_a": token_a,
        "token_b": token_b,
        "withdrawn_a": amt_a_return,
        "withdrawn_b": amt_b_return,
        "shares_burned": shares,
        "provider": provider,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)

    try:
        broadcast_tx(tx)
    except Exception:
        pass

    return jsonify(
        status="success",
        withdrawn_a=amt_a_return,
        withdrawn_b=amt_b_return,
        shares_burned=shares,
        remaining_shares=pool["providers"].get(provider, 0.0)
    ), 200


# ─── SWAP THROUGH POOL (AMM - AUTOMATED MARKET MAKER) ────────────────
@app.route("/api/v1/pools/swap", methods=["POST"])
def api_v1_pool_swap():
    """
    Swap tokens through a liquidity pool using constant product formula (x * y = k).
    Liquidity providers earn 0.3% fee on each swap.

    Request body:
    {
        "pool_id": "uuid...",
        "token_in": "THR",
        "token_out": "WBTC",
        "amount_in": 100.0,
        "min_amount_out": 0.0095,  // Slippage protection
        "trader_thr": "THR...",
        "auth_secret": "...",
        "passphrase": "..."
    }
    """
    data = request.get_json() or {}
    pool_id = (data.get("pool_id") or "").strip()
    token_in = (data.get("token_in") or "").upper().strip()
    token_out = (data.get("token_out") or "").upper().strip()
    amount_in_raw = data.get("amount_in", 0)
    min_amount_out_raw = data.get("min_amount_out", 0)
    trader = (data.get("trader_thr") or "").strip()
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    # Validate inputs
    try:
        amount_in = float(amount_in_raw)
        min_amount_out = float(min_amount_out_raw)
    except (TypeError, ValueError):
        return jsonify(status="error", message="Invalid amounts"), 400

    if not pool_id or not token_in or not token_out or amount_in <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    if token_in == token_out:
        return jsonify(status="error", message="Cannot swap same token"), 400

    if not trader or not auth_secret:
        return jsonify(status="error", message="Missing trader or auth_secret"), 400

    # Authenticate
    pledges = load_json(PLEDGE_CHAIN, [])
    trader_pledge = next((p for p in pledges if p.get("thr_address") == trader), None)
    if not trader_pledge:
        return jsonify(status="error", message="Trader has not pledged"), 404

    stored_auth_hash = trader_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(status="error", message="Trader send not enabled"), 400

    if trader_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(status="error", message="Passphrase required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify(status="error", message="Invalid auth"), 403

    # Load pool
    pools = load_pools()
    pool = next((p for p in pools if p.get("id") == pool_id), None)
    if not pool:
        return jsonify(status="error", message="Pool not found"), 404

    token_a = pool["token_a"]
    token_b = pool["token_b"]
    reserves_a = float(pool["reserves_a"])
    reserves_b = float(pool["reserves_b"])

    # Determine which token is which
    if token_in == token_a and token_out == token_b:
        reserve_in = reserves_a
        reserve_out = reserves_b
        is_a_to_b = True
    elif token_in == token_b and token_out == token_a:
        reserve_in = reserves_b
        reserve_out = reserves_a
        is_a_to_b = False
    else:
        return jsonify(
            status="error",
            message=f"Pool does not support {token_in}/{token_out} pair",
            pool_tokens=f"{token_a}/{token_b}"
        ), 400

    # Calculate swap using constant product formula with 0.3% fee
    # Formula: amount_out = (reserve_out * amount_in * 0.997) / (reserve_in + amount_in * 0.997)
    # 0.3% fee goes to liquidity providers
    FEE = 0.997  # 1 - 0.003 (0.3% fee)

    amount_in_with_fee = amount_in * FEE
    amount_out = (reserve_out * amount_in_with_fee) / (reserve_in + amount_in_with_fee)

    # Slippage protection
    if amount_out < min_amount_out:
        return jsonify(
            status="error",
            message="Slippage too high",
            expected_minimum=min_amount_out,
            actual_output=amount_out,
            price_impact=f"{((1 - amount_out/min_amount_out) * 100):.2f}%" if min_amount_out > 0 else "N/A"
        ), 400

    # Check trader has enough balance
    thr_ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    token_balances = load_token_balances()

    def get_balance(sym):
        if sym == "THR":
            return float(thr_ledger.get(trader, 0.0))
        elif sym == "WBTC":
            return float(wbtc_ledger.get(trader, 0.0))
        else:
            return float(token_balances.get(sym, {}).get(trader, 0.0))

    if get_balance(token_in) < amount_in:
        return jsonify(
            status="error",
            message=f"Insufficient {token_in} balance",
            your_balance=get_balance(token_in),
            required=amount_in
        ), 400

    # Execute swap - deduct input token, credit output token
    def deduct(sym, amt):
        if sym == "THR":
            thr_ledger[trader] = round(float(thr_ledger.get(trader, 0.0)) - amt, 6)
        elif sym == "WBTC":
            wbtc_ledger[trader] = round(float(wbtc_ledger.get(trader, 0.0)) - amt, 6)
        else:
            token_balances.setdefault(sym, {})
            token_balances[sym][trader] = round(float(token_balances[sym].get(trader, 0.0)) - amt, 6)

    def credit(sym, amt):
        if sym == "THR":
            thr_ledger[trader] = round(float(thr_ledger.get(trader, 0.0)) + amt, 6)
        elif sym == "WBTC":
            wbtc_ledger[trader] = round(float(wbtc_ledger.get(trader, 0.0)) + amt, 6)
        else:
            token_balances.setdefault(sym, {})
            token_balances[sym][trader] = round(float(token_balances[sym].get(trader, 0.0)) + amt, 6)

    deduct(token_in, amount_in)
    credit(token_out, amount_out)

    save_json(LEDGER_FILE, thr_ledger)
    save_json(WBTC_LEDGER_FILE, wbtc_ledger)
    save_token_balances(token_balances)

    # Update pool reserves (the fee stays in the pool, increasing value for LPs)
    if is_a_to_b:
        pool["reserves_a"] = round(reserves_a + amount_in, 6)
        pool["reserves_b"] = round(reserves_b - amount_out, 6)
    else:
        pool["reserves_b"] = round(reserves_b + amount_in, 6)
        pool["reserves_a"] = round(reserves_a - amount_out, 6)

    save_pools(pools)

    # Calculate fee earned by LPs (stays in pool)
    fee_amount = amount_in * (1 - FEE)  # 0.3% of input

    # Calculate price impact
    price_before = reserve_out / reserve_in if reserve_in > 0 else 0
    price_after = float(pool["reserves_b"] if is_a_to_b else pool["reserves_a"]) / float(pool["reserves_a"] if is_a_to_b else pool["reserves_b"])
    price_impact = abs(price_after - price_before) / price_before * 100 if price_before > 0 else 0

    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tx_id = f"POOL-SWAP-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "pool_swap",
        "pool_id": pool_id,
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": amount_in,
        "amount_out": amount_out,
        "fee": fee_amount,
        "fee_percent": 0.003,
        "price_impact": round(price_impact, 4),
        "trader": trader,
        "timestamp": ts,
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)

    try:
        broadcast_tx(tx)
    except Exception:
        pass

    return jsonify(
        status="success",
        amount_in=amount_in,
        amount_out=amount_out,
        fee=fee_amount,
        price_impact=f"{price_impact:.2f}%",
        new_balance_in=get_balance(token_in),
        new_balance_out=get_balance(token_out),
        tx_id=tx_id
    ), 200


# Run AI Wallet Check on Startup
ensure_ai_wallet()
recompute_height_offset_from_ledger()  # <-- Initialize offset


# This block fixes the 400/404 errors in chat by:
# 1. Supporting guest sessions (no wallet required)
# 2. Adding /api/ai/files/upload endpoint
# 3. Adding /api/ai/chat alias
# 4. Ensuring all /api/ai/sessions/* routes work correctly

from flask import make_response

def _current_actor_id(wallet: str | None) -> tuple[str, str | None]:
    """
    Returns (identity_key, guest_id or None).
    If no wallet provided, uses guest id for anonymous usage.
    """
    wallet = (wallet or "").strip()
    guest_id = None
    if not wallet:
        guest_id = get_or_set_guest_id()
        wallet = f"GUEST:{guest_id}"
    return wallet, guest_id


@app.route("/api/thrai/ask", methods=["POST"])
def api_thrai_ask():
    """
    Lightweight endpoint για τον Quantum Agent (Thrai).
    Χρησιμοποιείται ΜΟΝΟ από το CUSTOM_MODEL_URL του ai_agent_service.
    Δεν καλεί ξανά το /api/chat για να αποφύγουμε recursion.
    """
    start = time.time()
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []
    lang = (data.get("lang") or "el").strip()
    session_id = (data.get("session_id") or "").strip() or None

    if not prompt:
        return jsonify(ok=False, error="prompt required"), 400

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key or not anthropic:
        return jsonify(ok=False, error="ANTHROPIC_API_KEY not configured"), 500

    try:
        client = anthropic.Anthropic(api_key=api_key)
        messages = []
        for h in history[-10:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        model = os.getenv("THRAI_MODEL", "claude-3-sonnet-20240229")
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0.3,
            system="You are the Thronos Quantum Architect (Thrai). Answer clearly and concretely, in the language of the user.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")

        latency_ms = int((time.time() - start) * 1000)
        return jsonify(
            ok=True,
            response=text,
            model=model,
            latency_ms=latency_ms,
            session_id=session_id,
        ), 200
    except Exception as e:
        app.logger.exception("Thrai agent error")
        return jsonify(ok=False, error=str(e)), 500


# Override existing /api/ai/sessions routes with v2 versions that support guests
@app.route("/api/ai/sessions", methods=["GET", "POST"])
def api_ai_sessions_combined():
    """Handle both GET (list) and POST (create) for sessions"""
    if request.method == "GET":
        # List sessions for current user (wallet or guest)
        wallet = request.args.get("wallet") or None
        identity, guest_id = _current_actor_id(wallet)

        sessions = load_ai_sessions()
        user_sessions = []
        orphan_ids = set()

        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue

            if session_messages_exists(sid):
                if s.get("wallet") == identity and not s.get("archived"):
                    user_sessions.append(s)
            else:
                orphan_ids.add(sid)
                # Optional cleanup of the index for orphaned sessions
                remove_session_from_index(sid, wallet=identity)

        if orphan_ids:
            sessions = [s for s in sessions if s.get("id") not in orphan_ids]
            save_ai_sessions(sessions)

        # Sort by updated_at (newest first)
        user_sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

        resp = make_response(jsonify({"ok": True, "sessions": user_sessions}))
        if guest_id:
            resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp

    elif request.method == "POST":
        # Create new session
        data = request.get_json(silent=True) or {}
        wallet_in = data.get("wallet")
        identity, guest_id = _current_actor_id(wallet_in)

        title = (data.get("title") or "New Chat").strip()[:120]
        model = (data.get("model") or "auto").strip()

        sessions = load_ai_sessions()
        session_id = f"sess_{secrets.token_hex(8)}"
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        session = {
            "id": session_id,
            "wallet": identity,
            "title": title,
            "model": model,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "archived": False,
            "meta": {},
        }
        sessions.append(session)
        save_ai_sessions(sessions)
        ensure_session_messages_file(session_id)

        resp = make_response(jsonify({"ok": True, "id": session_id, "session": session}))
        if guest_id:
            resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp



@app.route("/api/chat/session/<session_id>/messages", methods=["GET", "POST"])
def api_ai_session_messages(session_id):
    """Get messages for a specific session"""
    wallet_in = (request.args.get("wallet") or "").strip()
    identity, guest_id = _current_actor_id(wallet_in)

    sessions = load_ai_sessions()
    session = None
    for s in sessions:
        if (
            s.get("id") == session_id
            and not s.get("archived")
            and s.get("wallet") == identity
        ):
            session = s
            break

    if not session:
        return jsonify({"ok": False, "error": "Session not found"}), 404

    ensure_session_messages_file(session_id)
    messages = load_session_messages(session_id)

    resp = make_response(jsonify({"ok": True, "session": session, "messages": messages}))
    if guest_id:
        resp.set_cookie(
            GUEST_COOKIE_NAME,
            guest_id,
            max_age=GUEST_TTL_SECONDS,
            httponly=True,
            samesite="Lax",
        )
    return resp


@app.route("/api/ai/sessions/<session_id>", methods=["PATCH"])
def api_ai_session_update(session_id):
    """Update session (e.g., rename)"""
    data = request.get_json(silent=True) or {}
    new_title = (data.get("title") or "").strip()

    if not new_title:
        return jsonify({"ok": False, "error": "Missing title"}), 400

    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("id") == session_id:
            s["title"] = new_title[:120]
            s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            found = True
            break

    if not found:
        return jsonify({"ok": False, "error": "Session not found"}), 404

    save_ai_sessions(sessions)
    return jsonify({"ok": True})


@app.route("/api/ai/sessions/<session_id>", methods=["DELETE"])
def api_ai_session_delete_by_id(session_id):
    """Delete/archive a session by ID using DELETE method"""
    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("id") == session_id:
            s["archived"] = True
            s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            found = True
            break

    if not found:
        return jsonify({"ok": False, "error": "Session not found"}), 404

    save_ai_sessions(sessions)
    return jsonify({"ok": True})


@app.route("/api/ai/sessions/start", methods=["POST"])
def api_ai_session_start_v2():
    """Start new session (supports both wallet and guest mode)"""
    data = request.get_json(silent=True) or {}
    wallet_in = data.get("wallet")
    identity, guest_id = _current_actor_id(wallet_in)

    title = (data.get("title") or "New Chat").strip()[:120]
    model = (data.get("model") or "auto").strip()

    sessions = load_ai_sessions()
    session_id = f"sess_{secrets.token_hex(8)}"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    session = {
        "id": session_id,
        "wallet": identity,
        "title": title,
        "model": model,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "archived": False,
        "meta": {},
    }
    sessions.append(session)
    save_ai_sessions(sessions)
    ensure_session_messages_file(session_id)

    resp = make_response(jsonify({"ok": True, "session": session}))
    if guest_id:
        resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
    return resp


@app.route("/api/chat/session/new", methods=["POST"])
def api_chat_session_new():
    """
    Alias wrapper πάνω από το POST /api/ai/sessions (v2) για το νέο /chat UI.
    ΔΕΝ απαιτεί οπωσδήποτε wallet – υποστηρίζει και guest.
    """
    data = request.get_json(silent=True) or {}
    wallet_in = data.get("wallet")
    title = (data.get("title") or "New Chat").strip()[:120]
    model = (data.get("model") or "auto").strip()

    identity, guest_id = _current_actor_id(wallet_in)
    sessions = load_ai_sessions()
    session_id = f"sess_{secrets.token_hex(8)}"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    session = {
        "id": session_id,
        "wallet": identity,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "archived": False,
    }
    sessions.append(session)
    save_ai_sessions(sessions)
    ensure_session_messages_file(session_id)

    resp = make_response(jsonify(ok=True, session=session))
    if guest_id:
        resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
    return resp, 200


@app.route("/api/chat/session", methods=["POST"])
def api_chat_session_alias():
    """Alias for creating a new chat session (compatibility with older UI)."""
    return api_chat_session_new()


@app.route("/api/chat/session/<session_id>", methods=["GET", "DELETE", "PATCH"])
def api_chat_session_get(session_id):
    """
    GET: Επιστρέφει session + πρόσφατο ιστορικό από το ai_offline_corpus.json.
    DELETE: Archives/deletes a session.
    PATCH: Renames a session.
    Χρησιμοποιεί είτε wallet είτε guest cookie για να φιλτράρει.
    """
    # Handle DELETE
    if request.method == "DELETE":
        wallet_in = request.args.get("wallet") or ""
        identity, guest_id = _current_actor_id(wallet_in)

        sessions = load_ai_sessions()
        found = False
        for s in sessions:
            if s.get("id") == session_id:
                # Verify ownership
                if s.get("wallet") != identity and not s.get("wallet", "").startswith("GUEST:"):
                    if identity != s.get("wallet"):
                        return jsonify(ok=False, error="Not authorized"), 403
                s["archived"] = True
                s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                found = True
                break

        if not found:
            return jsonify(ok=False, error="Session not found"), 404

        save_ai_sessions(sessions)
        resp = make_response(jsonify(ok=True))
        if guest_id:
            resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp, 200

    # Handle PATCH (rename)
    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        wallet_in = data.get("wallet") or request.args.get("wallet") or ""
        new_title = (data.get("title") or "").strip()

        if not new_title:
            return jsonify(ok=False, error="Missing title"), 400

        identity, guest_id = _current_actor_id(wallet_in)

        sessions = load_ai_sessions()
        found = False
        for s in sessions:
            if s.get("id") == session_id:
                if s.get("wallet") != identity and not s.get("wallet", "").startswith("GUEST:"):
                    if identity != s.get("wallet"):
                        return jsonify(ok=False, error="Not authorized"), 403
                s["title"] = new_title[:120]
                s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                found = True
                break

        if not found:
            return jsonify(ok=False, error="Session not found"), 404

        save_ai_sessions(sessions)
        resp = make_response(jsonify(ok=True))
        if guest_id:
            resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
        return resp, 200
    wallet_in = (request.args.get("wallet") or "").strip()
    identity, guest_id = _current_actor_id(wallet_in)

    sessions = load_ai_sessions()
    session = None
    for s in sessions:
        if s.get("id") == session_id and s.get("wallet") == identity and not s.get("archived"):
            session = s
            break
    if not session:
        return jsonify(ok=False, error="session not found"), 404

    corpus = load_json(AI_CORPUS_FILE, [])
    history = []
    for entry in corpus:
        if (entry.get("wallet") or identity) != identity:
            continue
        if (entry.get("session_id") or "default") != session_id:
            continue
        p = entry.get("prompt") or ""
        r = entry.get("response") or ""
        if p:
            history.append({"role": "user", "content": p})
        if r:
            history.append({"role": "assistant", "content": r})

    history = history[-40:]
    resp = make_response(jsonify(ok=True, session=session, messages=history))
    if guest_id:
        resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
    return resp, 200


@app.route("/api/chat/sessions", methods=["GET"])
def api_chat_sessions_list():
    """
    Λίστα sessions για το /chat UI (wallet ή guest).
    """
    wallet_in = (request.args.get("wallet") or "").strip()
    identity, guest_id = _current_actor_id(wallet_in)

    sessions = load_ai_sessions()
    out = []
    for s in sessions:
        if s.get("wallet") != identity or s.get("archived"):
            continue
        out.append(s)

    out.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "", reverse=True)
    resp = make_response(jsonify(ok=True, sessions=out))
    if guest_id:
        resp.set_cookie(GUEST_COOKIE_NAME, guest_id, max_age=GUEST_TTL_SECONDS, httponly=True, samesite="Lax")
    return resp, 200


@app.route("/api/ai/sessions/rename", methods=["POST"])
def api_ai_session_rename_v2():
    """Rename a session"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("id") or data.get("session_id")
    new_title = (data.get("title") or "").strip()
    wallet = data.get("wallet")

    if not session_id or not new_title:
        return jsonify({"ok": False, "error": "Missing id or title"}), 400

    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("id") == session_id:
            # Optional: verify ownership if wallet provided
            if wallet and s.get("wallet") != wallet and not s.get("wallet", "").startswith("GUEST:"):
                return jsonify({"ok": False, "error": "Not authorized"}), 403
            
            s["title"] = new_title[:120]
            s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            found = True
            break
    
    if not found:
        return jsonify({"ok": False, "error": "Session not found"}), 404
    
    save_ai_sessions(sessions)
    return jsonify({"ok": True})


@app.route("/api/ai/sessions/delete", methods=["POST"])
def api_ai_session_delete_v2():
    """Delete/archive a session"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("id") or data.get("session_id")
    wallet = data.get("wallet")

    if not session_id:
        return jsonify({"ok": False, "error": "Missing id"}), 400

    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("id") == session_id:
            # Optional: verify ownership
            if wallet and s.get("wallet") != wallet and not s.get("wallet", "").startswith("GUEST:"):
                return jsonify({"ok": False, "error": "Not authorized"}), 403
            
            s["archived"] = True
            s["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            found = True
            break
    
    if not found:
        return jsonify({"ok": False, "error": "Session not found"}), 404
    
    save_ai_sessions(sessions)
    return jsonify({"ok": True})


# Add file upload endpoint
# Add /api/ai/chat as alias to /api/chat (for backward compatibility)
@app.route("/api/ai/providers/chat", methods=["POST"])
def api_ai_provider_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    if prompt and not messages:
        messages = [{"role": "user", "content": prompt}]
    if not isinstance(messages, list) or not messages:
        return jsonify({"ok": False, "error": "messages required"}), 400

    model = (data.get("model") or data.get("model_key") or None) or "auto"
    max_tokens = int(data.get("max_tokens") or 1024)
    temperature = float(data.get("temperature") or 0.6)
    session_id = data.get("session_id")

    resolved_model = _resolve_model(model)
    if not resolved_model:
        return jsonify({"error": "Unknown or disabled model id"}), 400

    # FIX 1A: Process file attachments and include in context
    attachments = data.get("attachments", [])
    file_contexts = []
    if attachments:
        ai_files_dir = os.path.join(DATA_DIR, "ai_files")
        os.makedirs(ai_files_dir, exist_ok=True)
        for file_id in attachments:
            file_path = os.path.join(ai_files_dir, file_id)
            if os.path.exists(file_path):
                try:
                    # Try to read as text
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(10000)  # Limit to 10KB per file
                        file_contexts.append(f"[ATTACHED FILE: {file_id}]\n{content}\n[/FILE]")
                except Exception as e:
                    app.logger.warning(f"Failed to read file {file_id}: {e}")
                    file_contexts.append(f"[ATTACHED FILE: {file_id}] (binary or unreadable)")

    # Prepend file contexts to the user's message
    if file_contexts and messages:
        last_user_msg = messages[-1]
        if last_user_msg.get("role") == "user":
            file_context_str = "\n\n".join(file_contexts)
            last_user_msg["content"] = file_context_str + "\n\n" + last_user_msg["content"]

    # FIX 1A: Save user message to session with proper ID and deduplication
    if session_id and messages:
        existing_messages = load_session_messages(session_id)
        last_msg = messages[-1]  # Last message should be user message

        # Add metadata if missing
        if "timestamp" not in last_msg:
            last_msg["timestamp"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        if "msg_id" not in last_msg:
            last_msg["msg_id"] = f"msg_{int(time.time()*1000)}_{secrets.token_hex(4)}"

        # Deduplicate by msg_id (if exists) or by content+role+timestamp
        is_duplicate = False
        if last_msg.get("msg_id"):
            is_duplicate = any(m.get("msg_id") == last_msg.get("msg_id") for m in existing_messages)
        else:
            # Fallback: check content+role only for messages from same second
            is_duplicate = any(
                m.get("content") == last_msg.get("content") and
                m.get("role") == last_msg.get("role") and
                m.get("timestamp", "")[:19] == last_msg.get("timestamp", "")[:19]  # Same second
                for m in existing_messages
            )

        if not is_duplicate:
            existing_messages.append(last_msg)
            save_session_messages(session_id, existing_messages)
            app.logger.debug(f"Saved user message to session {session_id}: {last_msg.get('msg_id')}")

    try:
        result = call_llm(
            resolved_model.id,
            messages,
            system_prompt=(data.get("system_prompt") or None),
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
            wallet=data.get("wallet"),
            difficulty=data.get("difficulty"),
            block_hash=data.get("block_hash"),
        )
    except Exception as exc:
        app.logger.exception("AI provider chat failed")
        return (
            jsonify(
                {
                    "response": "Quantum Core Internal Error",
                    "status": "internal_error",
                    "error": str(exc),
                }
            ),
            500,
        )

    # FIX A2: Save assistant response to session with proper ID and deduplication
    if session_id and result.get("message"):
        existing_messages = load_session_messages(session_id)
        assistant_msg = {
            "role": "assistant",
            "content": result.get("message"),
            "model": result.get("model", model),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "msg_id": f"msg_{int(time.time()*1000)}_{secrets.token_hex(4)}"
        }

        # Deduplicate by msg_id or content+role+timestamp
        is_duplicate = False
        if assistant_msg.get("msg_id"):
            is_duplicate = any(m.get("msg_id") == assistant_msg.get("msg_id") for m in existing_messages)
        if not is_duplicate:
            # Fallback: check content+role from same second
            is_duplicate = any(
                m.get("content") == assistant_msg.get("content") and
                m.get("role") == assistant_msg.get("role") and
                m.get("timestamp", "")[:19] == assistant_msg.get("timestamp", "")[:19]
                for m in existing_messages
            )

        if not is_duplicate:
            existing_messages.append(assistant_msg)
            save_session_messages(session_id, existing_messages)
            app.logger.debug(f"Saved assistant message to session {session_id}: {assistant_msg.get('msg_id')}")

    return jsonify({"ok": True, **result})


@app.route("/api/ai/chat", methods=["POST"])
def api_ai_chat_alias():
    """Alias for /api/chat endpoint"""
    return api_chat()


# AI Wallet endpoint - returns current connected wallet info
@app.route("/api/ai/wallet", methods=["GET"])
def api_ai_wallet():
    """Return wallet information for AI chat interface"""
    thr_wallet = request.cookies.get("thr_address") or ""

    if not thr_wallet:
        return jsonify({
            "connected": False,
            "wallet": None,
            "balance": 0,
            "message": "No wallet connected"
        })

    # Get wallet balance from ledger
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(thr_wallet, 0.0))

    # Get pledge info if available
    pledges = load_json(PLEDGE_CHAIN, [])
    pledge = next((p for p in pledges if p.get("thr_address") == thr_wallet), None)

    return jsonify({
        "connected": True,
        "wallet": thr_wallet,
        "balance": round(balance, 6),
        "has_pledge": pledge is not None,
        "pledge_date": pledge.get("timestamp") if pledge else None
    })


# AI Telemetry endpoint - returns network statistics for AI interface
@app.route("/api/ai/telemetry", methods=["GET"])
def api_ai_telemetry():
    """Return network telemetry for AI chat interface"""
    try:
        # Get wallet from cookie to check AI credits
        thr_wallet = request.cookies.get("thr_address") or ""
        ai_credits = 0
        if thr_wallet:
            credits_map = load_ai_credits()
            try:
                ai_credits = int(credits_map.get(thr_wallet, 0) or 0)
            except (TypeError, ValueError):
                ai_credits = 0

        # Get network stats
        chain = load_json(CHAIN_FILE, [])
        mempool_data = load_json(MEMPOOL_FILE, [])
        pending_txs = len(mempool_data)

        # Calculate difficulty and hashrate (same logic as /api/network_live)
        blocks = chain
        target = get_mining_target()
        difficulty = int(INITIAL_TARGET // target)
        hashrate = 0

        # Calculate hashrate from recent blocks
        if len(blocks) >= 10:
            tail = blocks[-10:]
            try:
                from datetime import datetime
                t_fmt = "%Y-%m-%d %H:%M:%S UTC"
                t0 = datetime.strptime(tail[0]["timestamp"], t_fmt).timestamp()
                t1 = datetime.strptime(tail[-1]["timestamp"], t_fmt).timestamp()
                avg_time = (t1 - t0) / max(1, (len(tail) - 1))
                if avg_time and avg_time > 0:
                    hashrate = int(difficulty * (2**32) / avg_time)
            except Exception:
                hashrate = 0

        return jsonify({
            "hashrate": hashrate,
            "pending_txs": pending_txs,
            "difficulty": difficulty,
            "ai_credits": ai_credits
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/providers/health", methods=["GET"])
def api_ai_providers_health():
    providers = {"openai": "error", "anthropic": "error", "google": "error"}
    for name in providers.keys():
        providers[name] = _check_provider_health(name)
    return jsonify(providers)


def _get_fallback_models():
    """Return minimal curated model list for degraded mode."""
    try:
        from ai_models_config import CURATED_MODELS
        fallback = []
        for provider, data in CURATED_MODELS.items():
            for model in data.get("models", []):
                fallback.append({
                    "id": model["id"],
                    "provider": provider,
                    "label": model.get("label", model["id"]),
                    "display_name": model.get("label", model["id"]),
                    "enabled": False,  # Mark as disabled in degraded mode
                    "degraded": True,
                    "tier": "fallback",
                    "default": model.get("default", False),
                    "stats": {"total_calls": 0, "avg_latency_ms": 0.0}
                })
        return fallback
    except Exception as e:
        app.logger.error(f"Failed to load fallback models: {e}")
        return [{
            "id": "auto",
            "provider": "thronos",
            "label": "AUTO (Emergency Fallback)",
            "display_name": "AUTO (Emergency Fallback)",
            "enabled": True,
            "degraded": True,
            "tier": "emergency",
            "default": True,
            "stats": {"total_calls": 0, "avg_latency_ms": 0.0}
        }]


@app.route("/api/ai_models", methods=["GET"])
def api_ai_models():

    """
    Επιστρέφει ενοποιημένη λίστα μοντέλων για το Thronos Quantum UI.
    Χρησιμοποιεί το AI_MODEL_REGISTRY και τα stats από το AI Interaction Ledger.
    Δεν σκάει αν κάποιος provider δεν έχει API key – απλά τον μαρκάρει ως disabled.
    NEVER returns 500 - always returns 200 with degraded mode fallback if needed.
    """
    try:
        # Τι mode έχουμε ρυθμίσει στο node (π.χ. "all", "openai", "anthropic", "google")
        raw_mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
        if raw_mode in ("", "router", "auto"):
            mode = "all"
        else:
            mode = raw_mode

        # Βασικό config – ποιοι providers είναι ενεργοί στο σύστημα
        try:
           base_cfg = base_model_config() or {}

providers_cfg = base_cfg.get("providers")
if isinstance(providers_cfg, dict) and providers_cfg:
    enabled_providers = set(providers_cfg.keys())
else:
    enabled_providers = set(base_cfg.keys())  # <-- αυτό λείπει σήμερα

        except Exception as cfg_err:
            app.logger.warning(f"base_model_config failed: {cfg_err}")
            # Degraded mode fallback
            return jsonify({
                "ok": False,
                "mode": "degraded",
                "error_code": "PROVIDER_CONFIG_FAILED",
                "error_message": "Provider configuration unavailable",
                "providers": {},
                "models": _get_fallback_models(),
                "fallback_active": True
            }), 200

        # Στατιστικά ανά model id από το AI Interaction Ledger
        try:
            model_stats = compute_model_stats() or {}
        except Exception as stats_err:
            app.logger.warning(f"compute_model_stats failed: {stats_err}")
            model_stats = {}  # Continue without stats

        # FIX 7: Get provider_status early (contains source field)
        provider_status = get_provider_status()

        providers = {}
        models = []
        seen_models = set()  # FIX 7: Dedupe by (provider, model_id)

        # Για κάθε provider και τα μοντέλα του
        for provider_name, model_list in AI_MODEL_REGISTRY.items():
            # Αν έχουμε περιορισμένο mode, φιλτράρουμε (π.χ. μόνο "openai")
            if mode != "all" and provider_name != mode:
                continue

            provider_enabled = provider_name in enabled_providers

            # FIX 7: Get source from provider_status
            provider_source = provider_status.get(provider_name, {}).get("source", "registry")

            # Βασικά metadata provider για το UI
            providers[provider_name] = {
                "key": provider_name,
                "label": provider_name.capitalize(),
                "enabled": provider_enabled,
                "source": provider_source,  # FIX 7: Add source field for debugging
            }

            for mi in model_list:
                # FIX 7: Dedupe check - skip if (provider, model_id) already seen
                model_key = (mi.provider, mi.id)
                if model_key in seen_models:
                    app.logger.warning(f"Duplicate model skipped: {mi.provider}/{mi.id} (display: {mi.display_name})")
                    continue
                seen_models.add(model_key)

                # mi είναι ModelInfo dataclass από το llm_registry
                stats = model_stats.get(mi.id, {})
                models.append(
                    {
                        "id": mi.id,
                        "provider": mi.provider,
                        "label": mi.display_name,  # FIX: use display_name not label
                        "display_name": mi.display_name,
                        "tier": mi.tier,
                        "default": mi.default,
                        "enabled": provider_enabled and mi.enabled,  # FIX: use mi.enabled not mi.enabled_by_default
                        "stats": {
                            "total_calls": stats.get("total_calls", 0),
                            "avg_latency_ms": stats.get("avg_latency_ms", 0.0),
                        },
                    }
                )

        payload = {
            "ok": True,
            "mode": mode,
            "providers": providers,
            "provider_status": provider_status,  # New field for UI debugging
            "models": models,
            "fallback_active": False
        }
        return jsonify(payload), 200

    except Exception as exc:
        app.logger.exception("api_ai_models catastrophic error")
        # Last resort fallback - NEVER return 500
        return jsonify({
            "ok": False,
            "mode": "degraded",
            "error_code": "CATASTROPHIC_FAILURE",
            "error_message": str(exc),
            "providers": {},
            "models": _get_fallback_models(),
            "fallback_active": True
        }), 200  # ← ALWAYS 200, never 500

@app.route("/api/ai/feedback", methods=["POST"])
def api_ai_feedback():
    """Record user feedback (thumbs up/down) on AI responses"""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id", "")
        message_text = data.get("message_text", "")
        thumbs_up = data.get("thumbs_up", False)

        # Get wallet if available
        thr_wallet = request.cookies.get("thr_address") or ""

        # Create feedback entry
        feedback_entry = {
            "session_id": session_id,
            "wallet": thr_wallet,
            "message_text": message_text[:500],  # Truncate long messages
            "thumbs_up": thumbs_up,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }

        # Load existing feedback
        feedback_file = os.path.join(DATA_DIR, "ai_feedback.json")
        feedback_list = load_json(feedback_file, [])
        feedback_list.append(feedback_entry)

        # Save feedback
        save_json(feedback_file, feedback_list)

        return jsonify({"ok": True, "message": "Feedback recorded"})
    except Exception as e:
        app.logger.exception("Feedback error")
        return jsonify({"ok": False, "error": str(e)}), 500


# Update /chat route to pass wallet to template
@app.route("/chat")
def chat_page_v2():
    """Render chat interface with wallet from cookie"""
    thr_wallet = request.cookies.get("thr_address") or ""
    return render_template("chat.html", thr_wallet=thr_wallet)


# ─── DECENT MUSIC PLATFORM ────────────────────────────────────────────
# Decentralized music platform where artists can upload tracks and receive
# THR royalties from plays and tips from listeners.

MUSIC_FILE = os.path.join(DATA_DIR, "music_registry.json")


def load_music_registry():
    """Load music registry from file"""
    return load_json(MUSIC_FILE, {"tracks": [], "artists": {}, "plays": {}})


def save_music_registry(registry):
    """Save music registry to file"""
    save_json(MUSIC_FILE, registry)


def enrich_track_media(track: dict) -> dict:
    """Ensure track dictionaries expose media URLs from stored paths."""
    if track.get("audio_path") and not track.get("audio_url"):
        track["audio_url"] = f"/media/{track['audio_path']}"
    if track.get("cover_path"):
        track["cover_url"] = f"/media/{track['cover_path']}"
    return track


@app.route("/music")
def music_page():
    """Render the Decent Music platform"""
    return render_template("music.html")


@app.route("/api/v1/music/tracks")
def api_v1_music_tracks():
    """Get all published tracks"""
    registry = load_music_registry()
    tracks = [enrich_track_media(t) for t in registry["tracks"] if t.get("published", True)]
    # Add play counts
    for track in tracks:
        track["play_count"] = len(registry["plays"].get(track["id"], []))
    # Sort by newest first
    tracks.sort(key=lambda t: t.get("uploaded_at", ""), reverse=True)
    return jsonify({"status": "success", "tracks": tracks}), 200


@app.route("/api/v1/music/tracks/trending")
def api_v1_music_trending():
    """Get trending tracks (most plays in last 7 days)"""
    registry = load_music_registry()
    tracks = [enrich_track_media(t) for t in registry["tracks"] if t.get("published", True)]

    # Calculate recent play counts
    week_ago = time.time() - (7 * 24 * 60 * 60)
    for track in tracks:
        recent_plays = [p for p in registry["plays"].get(track["id"], [])
                       if float(p.get("timestamp", 0)) > week_ago]
        track["recent_plays"] = len(recent_plays)
        track["play_count"] = len(registry["plays"].get(track["id"], []))

    # Sort by recent plays
    tracks.sort(key=lambda t: t.get("recent_plays", 0), reverse=True)
    return jsonify({"status": "success", "tracks": tracks[:20]}), 200


@app.route("/api/v1/music/artist/<artist_address>")
def api_v1_music_artist(artist_address):
    """Get artist profile and tracks"""
    if not validate_thr_address(artist_address):
        return jsonify({"status": "error", "message": "Invalid address"}), 400

    registry = load_music_registry()
    artist = registry["artists"].get(artist_address, {})
    tracks = [enrich_track_media(t) for t in registry["tracks"] if t.get("artist_address") == artist_address]

    # Calculate stats
    total_plays = sum(len(registry["plays"].get(t["id"], [])) for t in tracks)
    total_earnings = float(artist.get("total_earnings", 0))

    return jsonify({
        "status": "success",
        "artist": artist,
        "tracks": tracks,
        "stats": {
            "total_tracks": len(tracks),
            "total_plays": total_plays,
            "total_earnings_thr": total_earnings
        }
    }), 200


@app.route("/api/v1/music/register_artist", methods=["POST"])
def api_v1_music_register_artist():
    """Register as an artist on the platform"""
    data = request.get_json() or {}
    address = (data.get("address") or "").strip()
    artist_name = (data.get("name") or "").strip()
    bio = (data.get("bio") or "").strip()

    if not address or not validate_thr_address(address):
        return jsonify({"status": "error", "message": "Invalid THR address"}), 400

    if not artist_name or len(artist_name) < 2:
        return jsonify({"status": "error", "message": "Artist name required (min 2 chars)"}), 400

    registry = load_music_registry()

    # Check if already registered
    if address in registry["artists"]:
        # Update profile
        registry["artists"][address]["name"] = artist_name
        registry["artists"][address]["bio"] = bio
    else:
        # New registration
        registry["artists"][address] = {
            "address": address,
            "name": artist_name,
            "bio": bio,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_earnings": 0,
            "verified": False
        }

    save_music_registry(registry)
    logger.info(f"Artist registered/updated: {artist_name} ({address})")

    return jsonify({
        "status": "success",
        "artist": registry["artists"][address]
    }), 200


@app.route("/api/v1/music/upload", methods=["POST"])
def api_v1_music_upload():
    """Upload a new track"""
    # Handle form data
    artist_address = (request.form.get("artist_address") or "").strip()
    title = (request.form.get("title") or "").strip()
    genre = (request.form.get("genre") or "Other").strip()
    description = (request.form.get("description") or "").strip()

    if not artist_address or not validate_thr_address(artist_address):
        return jsonify({"status": "error", "message": "Invalid artist address"}), 400

    if not title or len(title) < 2:
        return jsonify({"status": "error", "message": "Track title required"}), 400

    registry = load_music_registry()

    # Check if artist is registered
    if artist_address not in registry["artists"]:
        return jsonify({"status": "error", "message": "Please register as an artist first"}), 400

    # Handle audio file
    if "audio" not in request.files:
        return jsonify({"status": "error", "message": "Audio file required"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"status": "error", "message": "Empty filename"}), 400

    # Validate file type
    allowed_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}
    ext = os.path.splitext(secure_filename(audio_file.filename))[1].lower()
    if ext not in allowed_extensions:
        return jsonify({"status": "error", "message": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"}), 400

    try:
        # Generate track ID
        track_id = f"TRACK-{int(time.time())}-{secrets.token_hex(4)}"

        # Save audio file in persistent media volume
        audio_filename = f"{track_id}{ext}"
        audio_relative = os.path.join("music_audio", audio_filename)
        audio_file.save(os.path.join(MEDIA_DIR, audio_relative))

        # Handle cover art if provided (stored as <track_id>.jpg under music_covers)
        cover_relative = None
        if "cover" in request.files:
            cover_file = request.files["cover"]
            if cover_file.filename:
                cover_filename = f"{track_id}.jpg"
                cover_relative = os.path.join("music_covers", cover_filename)
                cover_file.save(os.path.join(MEDIA_DIR, cover_relative))

        # Create track entry
        track = {
            "id": track_id,
            "title": title,
            "artist_address": artist_address,
            "artist_name": registry["artists"][artist_address]["name"],
            "genre": genre,
            "description": description,
            "audio_path": audio_relative,
            "audio_url": f"/media/{audio_relative}",
            "cover_path": cover_relative,
            "cover_url": f"/media/{cover_relative}" if cover_relative else None,
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "published": True,
            "tips_total": 0
        }

        registry["tracks"].append(track)
        registry["plays"][track_id] = []
        save_music_registry(registry)

        logger.info(f"Track uploaded: {title} by {registry['artists'][artist_address]['name']}")

        return jsonify({
            "status": "success",
            "track": track
        }), 201

    except Exception as e:
        logger.error(f"Track upload error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500


@app.route("/api/v1/music/play/<track_id>", methods=["POST"])
def api_v1_music_play(track_id):
    """Record a track play and pay royalty to artist"""
    data = request.get_json() or {}
    listener_address = (data.get("listener_address") or "").strip()

    registry = load_music_registry()
    track = next((t for t in registry["tracks"] if t["id"] == track_id), None)

    if not track:
        return jsonify({"status": "error", "message": "Track not found"}), 404

    # Record play
    play = {
        "listener": listener_address or "anonymous",
        "timestamp": time.time(),
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }

    if track_id not in registry["plays"]:
        registry["plays"][track_id] = []
    registry["plays"][track_id].append(play)

    # Pay royalty (0.0001 THR per play from platform fund)
    PLAY_ROYALTY = 0.0001
    artist_address = track["artist_address"]

    try:
        ledger = load_json(LEDGER_FILE, {})
        ai_balance = float(ledger.get(AI_WALLET_ADDRESS, 0))

        if ai_balance >= PLAY_ROYALTY:
            # Pay artist from AI wallet
            ledger[AI_WALLET_ADDRESS] = round(ai_balance - PLAY_ROYALTY, 6)
            ledger[artist_address] = round(float(ledger.get(artist_address, 0)) + PLAY_ROYALTY, 6)
            save_json(LEDGER_FILE, ledger)

            # Update artist earnings
            if artist_address in registry["artists"]:
                registry["artists"][artist_address]["total_earnings"] = \
                    float(registry["artists"][artist_address].get("total_earnings", 0)) + PLAY_ROYALTY

            play["royalty_paid"] = PLAY_ROYALTY
    except Exception as e:
        logger.warning(f"Royalty payment failed: {e}")

    save_music_registry(registry)

    return jsonify({
        "status": "success",
        "play_count": len(registry["plays"].get(track_id, [])),
        "royalty_paid": play.get("royalty_paid", 0)
    }), 200


@app.route("/api/v1/music/tip", methods=["POST"])
def api_v1_music_tip():
    """Tip an artist for a track"""
    data = request.get_json() or {}
    track_id = (data.get("track_id") or "").strip()
    from_address = (data.get("from_address") or "").strip()
    amount = float(data.get("amount", 0))
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    if not track_id or not from_address or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid tip parameters"}), 400

    registry = load_music_registry()
    track = next((t for t in registry["tracks"] if t["id"] == track_id), None)

    if not track:
        return jsonify({"status": "error", "message": "Track not found"}), 404

    artist_address = track["artist_address"]

    # Verify auth
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_address), None)

    if not sender_pledge:
        return jsonify({"status": "error", "message": "Sender has not pledged"}), 400

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify({"status": "error", "message": "Send not enabled"}), 400

    if sender_pledge.get("has_passphrase"):
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"status": "error", "message": "Invalid auth"}), 403

    # Transfer THR
    ledger = load_json(LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_address, 0))

    if sender_balance < amount:
        return jsonify({"status": "error", "message": "Insufficient balance"}), 400

    ledger[from_address] = round(sender_balance - amount, 6)
    ledger[artist_address] = round(float(ledger.get(artist_address, 0)) + amount, 6)
    save_json(LEDGER_FILE, ledger)

    # Update track tips
    for t in registry["tracks"]:
        if t["id"] == track_id:
            t["tips_total"] = float(t.get("tips_total", 0)) + amount
            break

    # Update artist earnings
    if artist_address in registry["artists"]:
        registry["artists"][artist_address]["total_earnings"] = \
            float(registry["artists"][artist_address].get("total_earnings", 0)) + amount

    save_music_registry(registry)

    # Record transaction
    chain = load_json(CHAIN_FILE, [])
    tx_id = f"MUSIC-TIP-{int(time.time())}-{secrets.token_hex(4)}"
    tx = {
        "type": "music_tip",
        "track_id": track_id,
        "track_title": track["title"],
        "from": from_address,
        "to": artist_address,
        "amount": amount,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": tx_id,
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    logger.info(f"Music tip: {amount} THR from {from_address} to {artist_address} for track {track_id}")

    return jsonify({
        "status": "success",
        "tx_id": tx_id,
        "amount": amount,
        "new_balance": ledger[from_address]
    }), 200


@app.route("/api/v1/music/search")
def api_v1_music_search():
    """Search tracks by title, artist, or genre"""
    query = (request.args.get("q") or "").strip().lower()
    genre = (request.args.get("genre") or "").strip()

    if not query and not genre:
        return jsonify({"status": "error", "message": "Search query or genre required"}), 400

    registry = load_music_registry()
    tracks = registry["tracks"]

    results = []
    for track in tracks:
        if not track.get("published", True):
            continue

        match = False
        if query:
            if query in track.get("title", "").lower():
                match = True
            elif query in track.get("artist_name", "").lower():
                match = True
            elif query in track.get("genre", "").lower():
                match = True
            elif query in track.get("description", "").lower():
                match = True

        if genre and not match:
            if track.get("genre", "").lower() == genre.lower():
                match = True

        if match or (genre and track.get("genre", "").lower() == genre.lower()):
            track["play_count"] = len(registry["plays"].get(track["id"], []))
            results.append(track)

    return jsonify({
        "status": "success",
        "query": query,
        "genre": genre,
        "results": results
    }), 200


# ─── Token Explorer, NFT & Governance Pages ─────────────────────────────────

@app.route("/explorer")
def explorer_page():
    """Render the Token Explorer page"""
    return render_template("explorer.html")


@app.route("/nft")
def nft_page():
    """Render the NFT Marketplace page"""
    return render_template("nft.html")


@app.route("/governance")
def governance_page():
    """Render the Governance/DAO page"""
    return render_template("governance.html")


# ─── NFT API ─────────────────────────────────────────────────────────────────

NFT_REGISTRY_FILE = os.path.join(DATA_DIR, "nft_registry.json")

def load_nft_registry():
    return load_json(NFT_REGISTRY_FILE, {"nfts": [], "collections": {}})

def save_nft_registry(registry):
    save_json(NFT_REGISTRY_FILE, registry)


@app.route("/api/v1/nfts", methods=["GET"])
def api_v1_nfts():
    """Get all NFTs"""
    registry = load_nft_registry()
    return jsonify({"status": "success", "nfts": registry.get("nfts", [])}), 200


@app.route("/api/v1/nfts/mint", methods=["POST"])
def api_v1_nfts_mint():
    """Mint a new NFT"""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "art")
    price = float(request.form.get("price", 0))
    royalties = int(request.form.get("royalties", 10))
    creator = request.form.get("creator", "").strip()

    if not name or not creator:
        return jsonify({"status": "error", "message": "Name and creator required"}), 400

    # Handle image upload
    image_url = None
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext in ("png", "jpg", "jpeg", "gif", "webp"):
                nft_id = f"NFT{int(time.time() * 1000)}"
                filename = f"{nft_id}.{ext}"
                upload_dir = NFT_IMAGES_DIR
                os.makedirs(upload_dir, exist_ok=True)
                file.save(os.path.join(upload_dir, filename))
                image_url = f"/media/nft_images/{filename}"

    # Create NFT
    nft = {
        "id": f"NFT{int(time.time() * 1000)}",
        "name": name,
        "description": description,
        "category": category,
        "price": price,
        "royalties": royalties,
        "creator": creator,
        "owner": creator,
        "image_url": image_url,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "for_sale": True
    }

    registry = load_nft_registry()
    registry["nfts"].append(nft)
    save_nft_registry(registry)

    return jsonify({"status": "success", "nft": nft}), 201


@app.route("/api/v1/nfts/buy", methods=["POST"])
def api_v1_nfts_buy():
    """Buy an NFT"""
    data = request.get_json() or {}
    nft_id = data.get("nft_id", "").strip()
    buyer = data.get("buyer", "").strip()
    auth_secret = data.get("auth_secret", "").strip()

    if not nft_id or not buyer or not auth_secret:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    registry = load_nft_registry()
    nft = next((n for n in registry["nfts"] if n["id"] == nft_id), None)

    if not nft:
        return jsonify({"status": "error", "message": "NFT not found"}), 404

    if not nft.get("for_sale"):
        return jsonify({"status": "error", "message": "NFT not for sale"}), 400

    if nft["owner"] == buyer:
        return jsonify({"status": "error", "message": "You already own this NFT"}), 400

    # Transfer ownership
    old_owner = nft["owner"]
    nft["owner"] = buyer
    nft["for_sale"] = False
    save_nft_registry(registry)

    return jsonify({
        "status": "success",
        "message": f"NFT transferred from {old_owner} to {buyer}",
        "nft": nft
    }), 200


# ─── Governance API ──────────────────────────────────────────────────────────

GOVERNANCE_FILE = os.path.join(DATA_DIR, "governance.json")

def load_governance():
    return load_json(GOVERNANCE_FILE, {"proposals": [], "votes": {}})

def save_governance(gov):
    save_json(GOVERNANCE_FILE, gov)


@app.route("/api/v1/governance/proposals", methods=["GET"])
def api_v1_governance_proposals():
    """Get all governance proposals"""
    gov = load_governance()
    return jsonify({"status": "success", "proposals": gov.get("proposals", [])}), 200


@app.route("/api/v1/governance/proposals", methods=["POST"])
def api_v1_governance_create_proposal():
    """Create a new governance proposal"""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category = data.get("category", "other")
    duration_days = int(data.get("duration_days", 7))
    creator = data.get("creator", "").strip()

    if not title or not description or not creator:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    proposal = {
        "id": f"PROP{int(time.time() * 1000)}",
        "title": title,
        "description": description,
        "category": category,
        "status": "active",
        "votes_for": 0,
        "votes_against": 0,
        "creator": creator,
        "created_at": time.strftime("%Y-%m-%d", time.gmtime()),
        "ends_at": time.strftime("%Y-%m-%d", time.gmtime(time.time() + duration_days * 86400))
    }

    gov = load_governance()
    gov["proposals"].append(proposal)
    save_governance(gov)

    return jsonify({"status": "success", "proposal": proposal}), 201


@app.route("/api/v1/governance/vote", methods=["POST"])
def api_v1_governance_vote():
    """
    Vote on a proposal with THR burn and operator quorum enforcement.
    FIX G: Real governance voting (burn + quorum + on-chain)
    """
    data = request.get_json() or {}
    proposal_id = data.get("proposal_id", "").strip()
    voter = data.get("voter", "").strip()
    vote = data.get("vote", "").strip()  # "for", "against", "abstain"
    auth_secret = data.get("auth_secret", "").strip()
    passphrase = data.get("passphrase", "").strip()

    if not proposal_id or not voter or vote not in ("for", "against", "abstain"):
        return jsonify({"status": "error", "message": "Invalid vote data"}), 400

    if not auth_secret:
        return jsonify({"status": "error", "message": "auth_secret required for voting"}), 400

    # PRIORITY 2: Authenticate voter (log rejection reason)
    pledges = load_json(PLEDGE_CHAIN, [])
    voter_pledge = next((p for p in pledges if p.get("thr_address") == voter), None)
    if not voter_pledge:
        app.logger.warning(f"Vote rejected: auth_failed (not_pledged) | proposal={proposal_id} voter={voter}")
        return jsonify({"status": "error", "message": "Voter not pledged", "reason": "auth_failed"}), 404

    stored_auth_hash = voter_pledge.get("send_auth_hash")
    if voter_pledge.get("has_passphrase"):
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        app.logger.warning(f"Vote rejected: auth_failed (invalid_auth) | proposal={proposal_id} voter={voter}")
        return jsonify({"status": "error", "message": "Invalid auth", "reason": "auth_failed"}), 403

    # Load governance
    gov = load_governance()
    proposal = next((p for p in gov["proposals"] if p["id"] == proposal_id), None)

    if not proposal:
        return jsonify({"status": "error", "message": "Proposal not found"}), 404

    if proposal.get("status") not in ["OPEN", "QUORUM_PENDING", None, "active"]:
        return jsonify({"status": "error", "message": f"Proposal is {proposal.get('status', 'closed')}"}), 400

    # PRIORITY 2: Check if already voted (log rejection reason)
    vote_key = f"{proposal_id}:{voter}"
    if vote_key in gov.get("votes", {}):
        app.logger.warning(f"Vote rejected: already_voted | proposal={proposal_id} voter={voter}")
        return jsonify({"status": "error", "message": "Already voted on this proposal", "reason": "already_voted"}), 400

    # FIX G3: THR BURN PER VOTE
    # Determine if voter is operator
    OPERATORS = os.getenv("GOVERNANCE_OPERATORS", "").split(",")
    if not OPERATORS or OPERATORS == [""]:
        # Hardcoded fallback for dev
        OPERATORS = ["THR_OPERATOR_1", "THR_OPERATOR_2", "THR_OPERATOR_3"]

    is_operator = voter in OPERATORS
    burn_amount = 0.05 if is_operator else 0.01  # Higher burn for operators

    # PRIORITY 2: Check voter has enough balance (log rejection reason)
    ledger = load_json(LEDGER_FILE, {})
    voter_balance = float(ledger.get(voter, 0.0))
    if voter_balance < burn_amount:
        app.logger.warning(f"Vote rejected: insufficient_balance | proposal={proposal_id} voter={voter} balance={voter_balance} need={burn_amount}")
        return jsonify({"status": "error", "message": f"Insufficient balance. Need {burn_amount} THR to vote", "reason": "insufficient_balance"}), 400

    # Burn THR
    ledger[voter] = round(voter_balance - burn_amount, 6)
    save_json(LEDGER_FILE, ledger)

    # Write GOV_VOTE transaction on-chain
    chain = load_json(CHAIN_FILE, [])
    vote_tx = {
        "tx_id": f"GOV_VOTE_{proposal_id}_{int(time.time())}_{secrets.token_hex(4)}",
        "type": "GOV_VOTE",
        "proposal_id": proposal_id,
        "voter": voter,
        "vote": vote,
        "is_operator": is_operator,
        "burn_amount": burn_amount,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "block": len(chain) + 1
    }
    chain.append(vote_tx)
    save_json(CHAIN_FILE, chain)

    # Record vote in governance
    if "votes" not in gov:
        gov["votes"] = {}
    gov["votes"][vote_key] = {
        "vote": vote,
        "voter": voter,
        "is_operator": is_operator,
        "burn_amount": burn_amount,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": vote_tx["tx_id"]
    }

    # Update proposal counts
    if vote == "for":
        proposal["votes_for"] = proposal.get("votes_for", 0) + 1
    elif vote == "against":
        proposal["votes_against"] = proposal.get("votes_against", 0) + 1
    else:  # abstain
        proposal["votes_abstain"] = proposal.get("votes_abstain", 0) + 1

    # Track operator votes
    if "operator_votes" not in proposal:
        proposal["operator_votes"] = []
    if is_operator and vote != "abstain":
        proposal["operator_votes"].append({"voter": voter, "vote": vote, "timestamp": vote_tx["timestamp"]})

    # FIX G2: Check operator quorum
    MIN_OPERATOR_VOTES = int(os.getenv("MIN_OPERATOR_VOTES", "3"))
    operator_count = len(proposal.get("operator_votes", []))

    # Update proposal status
    if proposal.get("status") in [None, "active"]:
        proposal["status"] = "OPEN"

    if operator_count >= MIN_OPERATOR_VOTES:
        proposal["status"] = "QUORUM_REACHED"
        app.logger.info(f"QUORUM REACHED: Proposal {proposal_id} has {operator_count} operator votes")
    elif operator_count > 0:
        proposal["status"] = "QUORUM_PENDING"

    # Record total THR burned for this proposal
    proposal["total_burned"] = proposal.get("total_burned", 0.0) + burn_amount

    save_governance(gov)

    return jsonify({
        "status": "success",
        "message": "Vote recorded",
        "burned_thr": burn_amount,
        "tx_id": vote_tx["tx_id"],
        "proposal_status": proposal["status"],
        "operator_votes": operator_count,
        "quorum_required": MIN_OPERATOR_VOTES
    }), 200


@app.route("/api/v1/governance/finalize", methods=["POST"])
def api_v1_governance_finalize():
    """
    Finalize a proposal after quorum reached and voting window closed.
    FIX G4: On-chain finalization with GOV_FINALIZE transaction.
    """
    data = request.get_json() or {}
    proposal_id = data.get("proposal_id", "").strip()
    operator = data.get("operator", "").strip()
    auth_secret = data.get("auth_secret", "").strip()
    passphrase = data.get("passphrase", "").strip()

    if not proposal_id or not operator:
        return jsonify({"status": "error", "message": "proposal_id and operator required"}), 400

    # Authenticate operator
    pledges = load_json(PLEDGE_CHAIN, [])
    operator_pledge = next((p for p in pledges if p.get("thr_address") == operator), None)
    if not operator_pledge:
        return jsonify({"status": "error", "message": "Operator not pledged"}), 404

    stored_auth_hash = operator_pledge.get("send_auth_hash")
    if operator_pledge.get("has_passphrase"):
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest() != stored_auth_hash:
        return jsonify({"status": "error", "message": "Invalid auth"}), 403

    # Verify operator status
    OPERATORS = os.getenv("GOVERNANCE_OPERATORS", "").split(",")
    if not OPERATORS or OPERATORS == [""]:
        OPERATORS = ["THR_OPERATOR_1", "THR_OPERATOR_2", "THR_OPERATOR_3"]
    if operator not in OPERATORS:
        return jsonify({"status": "error", "message": "Not an operator"}), 403

    # Load governance
    gov = load_governance()
    proposal = next((p for p in gov["proposals"] if p["id"] == proposal_id), None)

    if not proposal:
        return jsonify({"status": "error", "message": "Proposal not found"}), 404

    # Check if quorum reached
    MIN_OPERATOR_VOTES = int(os.getenv("MIN_OPERATOR_VOTES", "3"))
    operator_count = len(proposal.get("operator_votes", []))

    if operator_count < MIN_OPERATOR_VOTES:
        return jsonify({
            "status": "error",
            "message": f"Quorum not reached. Need {MIN_OPERATOR_VOTES} operators, have {operator_count}"
        }), 400

    if proposal.get("status") == "FINALIZED":
        return jsonify({"status": "error", "message": "Already finalized"}), 400

    # Determine result
    votes_for = proposal.get("votes_for", 0)
    votes_against = proposal.get("votes_against", 0)
    result = "ACCEPTED" if votes_for > votes_against else "REJECTED"

    # FIX G4: Write GOV_FINALIZE transaction on-chain
    chain = load_json(CHAIN_FILE, [])
    finalize_tx = {
        "tx_id": f"GOV_FINALIZE_{proposal_id}_{int(time.time())}",
        "type": "GOV_FINALIZE",
        "proposal_id": proposal_id,
        "result": result,
        "votes_for": votes_for,
        "votes_against": votes_against,
        "votes_abstain": proposal.get("votes_abstain", 0),
        "operator_votes": operator_count,
        "total_burned": proposal.get("total_burned", 0.0),
        "finalized_by": operator,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "block": len(chain) + 1
    }
    chain.append(finalize_tx)
    save_json(CHAIN_FILE, chain)

    # Update proposal
    proposal["status"] = "FINALIZED"
    proposal["result"] = result
    proposal["finalized_at"] = finalize_tx["timestamp"]
    proposal["finalized_by"] = operator
    proposal["finalize_tx_id"] = finalize_tx["tx_id"]

    save_governance(gov)

    app.logger.info(f"FINALIZED: Proposal {proposal_id} result={result}, votes={votes_for}:{votes_against}")

    return jsonify({
        "status": "success",
        "result": result,
        "proposal_status": "FINALIZED",
        "tx_id": finalize_tx["tx_id"],
        "votes_for": votes_for,
        "votes_against": votes_against,
        "total_burned": proposal.get("total_burned", 0.0)
    }), 200


# ─── PYTHEIA Advice Schema & Ingestion ──────────────────────────────────────

@app.route("/schemas/pytheia-advice.schema.json")
def serve_pytheia_schema():
    """Serve PYTHEIA Advice JSON Schema"""
    schema_path = os.path.join(os.path.dirname(__file__), "schemas", "pytheia-advice.schema.json")
    if not os.path.exists(schema_path):
        return jsonify({"status": "error", "message": "Schema file not found"}), 404
    return send_file(schema_path, mimetype="application/schema+json")


@app.route("/api/governance/pytheia/advice", methods=["POST"])
def api_pytheia_advice():
    """
    Ingest PYTHEIA AI Node audit advice.
    Validates against pytheia-advice.schema.json and stores as special governance post.
    Returns: {"status": "success", "post_id": "...", "url": "..."}
    """
    data = request.get_json() or {}

    # Basic validation - check required fields per schema
    required = ["schema_version", "timestamp", "auditor", "repo", "commit",
                "title", "severity", "priorities", "options", "patch_plan"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}"
        }), 400

    # Validate schema_version
    if data.get("schema_version") != "PYTHEIA Advice v1.0.0":
        return jsonify({
            "status": "error",
            "message": "Invalid schema_version. Expected 'PYTHEIA Advice v1.0.0'"
        }), 400

    # Validate severity
    valid_severities = ["BLOCKER", "MAJOR", "MINOR", "INFO"]
    if data.get("severity") not in valid_severities:
        return jsonify({
            "status": "error",
            "message": f"Invalid severity. Must be one of: {', '.join(valid_severities)}"
        }), 400

    # Validate priorities array
    priorities = data.get("priorities", [])
    if not isinstance(priorities, list) or len(priorities) < 1 or len(priorities) > 20:
        return jsonify({
            "status": "error",
            "message": "priorities must be an array with 1-20 items"
        }), 400

    # Validate options array
    options = data.get("options", [])
    if not isinstance(options, list) or len(options) < 1 or len(options) > 5:
        return jsonify({
            "status": "error",
            "message": "options must be an array with 1-5 items"
        }), 400

    # Create governance post
    post_id = f"PYTHEIA{int(time.time() * 1000)}"

    # Build governance proposal from PYTHEIA advice
    proposal = {
        "id": post_id,
        "type": "PYTHEIA_ADVICE",  # Special type for rendering
        "title": data.get("title"),
        "description": f"Audit by {data.get('auditor')} - Severity: {data.get('severity')}",
        "category": "protocol",  # PYTHEIA advice is always protocol-related
        "status": "active" if data.get("requires_approval", True) else "info",
        "votes_for": 0,
        "votes_against": 0,
        "creator": data.get("auditor", "PYTHEIA AI Node"),
        "created_at": time.strftime("%Y-%m-%d", time.gmtime()),
        "ends_at": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 7 * 86400)),  # 7 days
        # Store full PYTHEIA data
        "pytheia_data": data
    }

    # Save to governance
    gov = load_governance()
    gov["proposals"].append(proposal)
    save_governance(gov)

    # Generate URL
    governance_url = data.get("governance_url") or "https://thrchain.up.railway.app/governance"

    return jsonify({
        "status": "success",
        "post_id": post_id,
        "url": governance_url,
        "message": "PYTHEIA advice posted to governance successfully"
    }), 201


# ... ΤΕΛΟΣ όλων των routes / helpers ...

print("✓ AI Session fixes loaded - supports guest mode and file uploads")
print("✓ Token Explorer, NFT Marketplace and Governance pages loaded")
print("✓ Decent Music Platform loaded - artist registration, uploads, and royalties")
# --- Startup hooks ---
refresh_model_catalog(force=True)
_start_model_scheduler()
ensure_ai_wallet()
recompute_height_offset_from_ledger()
initialize_voting()  # Initialize voting polls

if __name__ == "__main__":
    port = int(os.getenv("PORT", 13311))
    host = os.getenv("HOST", "0.0.0.0")
    app.run(host=host, port=port)

if __name__ == "__main__":
    port=int(os.getenv("PORT",3333))
    app.run(host="0.0.0.0", port=port)
# === AI Session API Fixes (append to end of server.py) ===========================

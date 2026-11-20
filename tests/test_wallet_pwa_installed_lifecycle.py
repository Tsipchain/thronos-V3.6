"""Installed PWA service-worker lifecycle acceptance in real Chromium."""

import mimetypes
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]


class _PwaHandler(BaseHTTPRequestHandler):
    serve_update = False

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/wallet-pwa/":
            target = ROOT / "public" / "wallet-pwa" / "index.html"
        elif path.startswith("/wallet-pwa/"):
            target = ROOT / "public" / path.lstrip("/")
        elif path.startswith("/static/"):
            target = ROOT / path.lstrip("/")
        else:
            self.send_error(404)
            return
        try:
            data = target.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            self.send_error(404)
            return
        if path == "/wallet-pwa/sw.js" and self.serve_update:
            data = data.replace(b"thr-wallet-pwa-v28", b"thr-wallet-pwa-v28-staging-update")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format, *_args):
        return


@pytest.fixture
def pwa_server():
    _PwaHandler.serve_update = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PwaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_installed_pwa_precaches_v2_contract_updates_and_reloads_offline(pwa_server):
    playwright = pytest.importorskip("playwright.sync_api")
    base_url = f"http://127.0.0.1:{pwa_server.server_port}"
    with playwright.sync_playwright() as runtime:
        executable = os.environ.get("WALLET_E2E_CHROMIUM") or shutil.which("chromium")
        launch_options = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        browser = runtime.chromium.launch(**launch_options)
        context = browser.new_context(service_workers="allow")
        page = context.new_page()
        page.goto(f"{base_url}/wallet-pwa/", wait_until="domcontentloaded")
        page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller")
        page.wait_for_function(
            "async () => (await caches.keys()).includes('thr-wallet-pwa-v28')"
        )
        assert page.evaluate(
            "async () => !!(await caches.match('/static/wallet_v1_full_payload_contract.js'))"
        )

        _PwaHandler.serve_update = True
        page.evaluate("async () => (await navigator.serviceWorker.getRegistration()).update()")
        page.wait_for_function(
            "async () => (await caches.keys()).includes('thr-wallet-pwa-v28-staging-update')"
        )
        page.wait_for_function(
            "async () => !(await caches.keys()).includes('thr-wallet-pwa-v28')"
        )

        context.set_offline(True)
        page.reload(wait_until="domcontentloaded")
        assert page.title() == "THR Wallet"
        assert page.evaluate("!!navigator.serviceWorker.controller") is True
        page.wait_for_function("document.querySelector('#root').children.length > 0")
        context.set_offline(False)
        browser.close()

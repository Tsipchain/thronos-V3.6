"""
Maker Agent — runs on the printer operator's machine.

Communicates with the Thronos node to manage the physical asset
production lifecycle: design submission, print management,
creator-signed certification.

Usage:
    agent = MakerAgent(node_url='http://192.168.1.10:5000',
                       private_key_hex='...')
    # or
    agent = MakerAgent.from_config('maker_config.json')

    # Full production flow
    batch = agent.create_batch('coin-v1', design_file='benchy.3mf', quantity=5)
    for job in batch['jobs']:
        agent.upload_gcode(job['job_id'], 'benchy.gcode')
        agent.start_print(job['job_id'], printer_id='BAMBU-X1C-001')
        # ... printer prints ...
        agent.complete_print(job['job_id'])
        agent.certify(job['job_id'])
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .signer import WalletSigner

logger = logging.getLogger(__name__)


class MakerAgent:
    def __init__(
        self,
        node_url: str,
        private_key_hex: str,
        tenant_id: str = 'default',
        printer_id: str = '',
        timeout: int = 30,
    ):
        self.node_url = node_url.rstrip('/')
        self.signer = WalletSigner(private_key_hex)
        self.tenant_id = tenant_id
        self.printer_id = printer_id
        self.timeout = timeout
        self.address = self.signer.address

        logger.info(f"Maker Agent initialized — address: {self.address}")

    @classmethod
    def from_config(cls, config_path: str) -> 'MakerAgent':
        with open(config_path, 'r') as f:
            cfg = json.load(f)

        key_hex = cfg.get('private_key', '')
        if not key_hex and cfg.get('key_file'):
            with open(cfg['key_file'], 'r') as kf:
                key_hex = kf.read().strip()

        return cls(
            node_url=cfg['node_url'],
            private_key_hex=key_hex,
            tenant_id=cfg.get('tenant_id', 'default'),
            printer_id=cfg.get('printer_id', ''),
            timeout=cfg.get('timeout', 30),
        )

    def _api(self, method: str, path: str, data: dict = None) -> dict:
        url = f"{self.node_url}/api/assets{path}"
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=self.timeout)
            else:
                resp = requests.post(url, json=data, timeout=self.timeout)
            result = resp.json()
            if not result.get('ok'):
                logger.warning(f"API error {path}: {result.get('error')} — {result.get('detail', '')}")
            return result
        except requests.RequestException as e:
            logger.error(f"Connection error {path}: {e}")
            return {'ok': False, 'error': 'connection_error', 'detail': str(e)}

    def _signed_post(self, path: str, action: str, payload: dict) -> dict:
        body = self.signer.build_signed_request(action, payload)
        return self._api('POST', path, body)

    @staticmethod
    def hash_file(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    # ── Design & batch creation ───────────────────────────────────────

    def create_batch(
        self,
        product_id: str,
        sku: str,
        design_file: str,
        quantity: int,
        edition_start: int = 1,
        edition_size: int = 100,
        creation_fee: float = 0.0,
        batch_id: str = None,
    ) -> dict:
        design_hash = self.hash_file(design_file)
        logger.info(f"Design hash ({os.path.basename(design_file)}): {design_hash}")

        if not batch_id:
            batch_id = f"BATCH-{int(time.time())}"

        _, ext = os.path.splitext(design_file)
        design_format = ext.lstrip('.').lower() or '3mf'

        payload = {
            'batch_id': batch_id,
            'tenant_id': self.tenant_id,
            'product_id': product_id,
            'sku': sku,
            'quantity': quantity,
            'edition_start': edition_start,
            'edition_size': edition_size,
            'design_hash': design_hash,
            'design_format': design_format,
            'creation_fee': creation_fee,
        }
        result = self._signed_post('/batches', 'physical_asset_produce', payload)
        if result.get('ok'):
            jobs = result.get('jobs', [])
            logger.info(f"Batch {batch_id} created — {len(jobs)} jobs")
            for j in jobs:
                logger.info(f"  Job {j['job_id']}: serial {j['serial']}")
        return result

    # ── Gcode upload ──────────────────────────────────────────────────

    def upload_gcode(self, job_id: str, gcode_file: str) -> dict:
        gcode_hash = self.hash_file(gcode_file)
        logger.info(f"Gcode hash ({os.path.basename(gcode_file)}): {gcode_hash}")

        payload = {'gcode_hash': gcode_hash}
        return self._signed_post(f'/jobs/{job_id}/gcode', 'physical_asset_produce', payload)

    # ── Print lifecycle ───────────────────────────────────────────────

    def start_print(self, job_id: str, printer_id: str = None) -> dict:
        pid = printer_id or self.printer_id
        if not pid:
            return {'ok': False, 'error': 'printer_id_required'}

        payload = {'printer_id': pid}
        result = self._signed_post(f'/jobs/{job_id}/start', 'physical_asset_produce', payload)
        if result.get('ok'):
            logger.info(f"Print started: {job_id} on {pid}")
        return result

    def complete_print(self, job_id: str) -> dict:
        payload = {}
        result = self._signed_post(f'/jobs/{job_id}/complete', 'physical_asset_produce', payload)
        if result.get('ok'):
            logger.info(f"Print completed: {job_id}")
        return result

    def fail_print(self, job_id: str, reason: str = '') -> dict:
        payload = {'reason': reason}
        result = self._signed_post(f'/jobs/{job_id}/fail', 'physical_asset_produce', payload)
        if result.get('ok'):
            logger.warning(f"Print failed: {job_id} — {reason}")
        return result

    # ── Creator signing & certification ─────────────────────────────────

    def _build_signature_data(self, job_id: str, job: dict) -> dict:
        import uuid
        return {
            'tenant_id': self.tenant_id,
            'batch_id': job.get('batch_id', ''),
            'job_id': job_id,
            'asset_id': job.get('asset_id', ''),
            'serial': job.get('serial', ''),
            'edition_number': job.get('edition_number', 0),
            'creator_address': self.address,
            'design_hash': job.get('design_hash', ''),
            'gcode_hash': job.get('gcode_hash', ''),
            'printer_id': job.get('printer_id', ''),
            'completed_at': job.get('completed_at', ''),
            'nonce': uuid.uuid4().hex,
        }

    def sign_production(self, job_id: str) -> dict:
        """Sign production attestation (PRINTED → CREATOR_SIGNED)."""
        status = self.get_job_status(job_id)
        if not status.get('ok'):
            return status

        job = status.get('job', {})

        if job.get('status') != 'PRINTED':
            return {'ok': False, 'error': 'job_not_ready',
                    'detail': f"job status is {job.get('status')}, need PRINTED"}

        signature_data = self._build_signature_data(job_id, job)
        payload = {'signature_data': signature_data}
        result = self._signed_post(f'/jobs/{job_id}/sign', 'physical_asset_produce', payload)
        if result.get('ok'):
            logger.info(f"Signed: {job_id}")
        return result

    def certify_production(self, job_id: str) -> dict:
        """Trigger canonical NFT mint (CREATOR_SIGNED → CERTIFIED)."""
        result = self._signed_post(f'/jobs/{job_id}/certify', 'physical_asset_produce', {})
        if result.get('ok'):
            nft_id = result.get('nft_id', '')
            tx_id = result.get('tx_id', '')
            if not result.get('certified'):
                logger.warning(f"Certify returned ok but certified=False: {job_id}")
                return {'ok': False, 'error': 'certification_incomplete',
                        'detail': 'server did not confirm certification'}
            if not nft_id or not tx_id:
                logger.warning(f"Certify missing nft_id or tx_id: {job_id}")
                return {'ok': False, 'error': 'certification_incomplete',
                        'detail': 'missing nft_id or tx_id'}
            logger.info(f"CERTIFIED: {job_id} → NFT {nft_id} tx {tx_id}")
        return result

    def certify(self, job_id: str) -> dict:
        """Full sign → certify flow (PRINTED → CREATOR_SIGNED → CERTIFIED)."""
        sign_result = self.sign_production(job_id)
        if not sign_result.get('ok'):
            return sign_result
        return self.certify_production(job_id)

    # ── Status queries ────────────────────────────────────────────────

    def get_batch(self, batch_id: str) -> dict:
        return self._api('GET', f'/batches/{batch_id}')

    def get_job(self, job_id: str) -> dict:
        return self._api('GET', f'/jobs/{job_id}')

    def get_job_status(self, job_id: str) -> dict:
        return self._api('GET', f'/jobs/{job_id}/status')

    def list_jobs(self, batch_id: str = None, status: str = None) -> dict:
        params = []
        if batch_id:
            params.append(f'batch_id={batch_id}')
        if status:
            params.append(f'status={status}')
        qs = '?' + '&'.join(params) if params else ''
        return self._api('GET', f'/jobs{qs}')

    # ── Full production run ───────────────────────────────────────────

    def run_full_production(
        self,
        product_id: str,
        sku: str,
        design_file: str,
        gcode_file: str,
        quantity: int = 1,
        edition_start: int = 1,
        edition_size: int = 100,
        creation_fee: float = 0.0,
        printer_id: str = None,
        auto_certify: bool = False,
    ) -> dict:
        """Run the full production flow for a batch.

        Steps: create batch → upload gcode per job → start print →
        (wait for manual complete) → optionally sign + certify.

        Creator must be pre-approved by a tenant admin before calling.
        In auto mode, all steps run sequentially (for testing).
        In normal mode, returns after starting prints —
        call complete_print() and certify() per job when ready.
        """
        logger.info(f"=== Production run: {product_id} x{quantity} ===")

        # Create batch (creator must be pre-approved by a tenant admin)
        batch = self.create_batch(
            product_id=product_id,
            sku=sku,
            design_file=design_file,
            quantity=quantity,
            edition_start=edition_start,
            edition_size=edition_size,
            creation_fee=creation_fee,
        )
        if not batch.get('ok'):
            return {'ok': False, 'error': 'batch_failed', 'detail': batch}

        jobs = batch.get('jobs', [])
        pid = printer_id or self.printer_id
        results = []

        for job in jobs:
            jid = job['job_id']

            # Upload gcode
            gc = self.upload_gcode(jid, gcode_file)
            if not gc.get('ok'):
                results.append({'job_id': jid, 'step': 'gcode', 'error': gc})
                continue

            # Start print
            sp = self.start_print(jid, pid)
            if not sp.get('ok'):
                results.append({'job_id': jid, 'step': 'start', 'error': sp})
                continue

            if auto_certify:
                cp = self.complete_print(jid)
                if not cp.get('ok'):
                    results.append({'job_id': jid, 'step': 'complete', 'error': cp})
                    continue

                cert = self.certify(jid)
                results.append({
                    'job_id': jid,
                    'certified': cert.get('certified', False),
                    'nft_id': cert.get('nft_id', ''),
                    'tx_id': cert.get('tx_id', ''),
                })
            else:
                results.append({'job_id': jid, 'status': 'PRINTING',
                                'serial': job.get('serial')})

        return {
            'ok': True,
            'batch_id': batch.get('batch', {}).get('batch_id'),
            'jobs': results,
        }

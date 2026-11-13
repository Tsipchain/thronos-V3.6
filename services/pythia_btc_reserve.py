"""Read-only BTC reserve verification for Pythia settlement policy.

Uses the existing BTC JSON-RPC credentials to inspect confirmed UTXOs of a
dedicated settlement reserve address.  It cannot sign, broadcast, move BTC,
or access a private key.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import os
import time
from typing import Any, Protocol

SATOSHI = Decimal("0.00000001")


class BtcReserveError(RuntimeError):
    pass


class BitcoinRpc(Protocol):
    def call(self, method: str, params: list[Any]) -> Any:
        ...


@dataclass(frozen=True)
class BtcReserveSnapshot:
    address: str
    confirmed_btc: Decimal
    confirmed_sats: int
    utxo_count: int
    min_confirmations: int
    observed_at: int
    source: str = "bitcoin_rpc"

    def public_dict(self) -> dict[str, str | int]:
        return {
            "address": self.address,
            "confirmed_btc": str(self.confirmed_btc.quantize(SATOSHI)),
            "confirmed_sats": self.confirmed_sats,
            "utxo_count": self.utxo_count,
            "min_confirmations": self.min_confirmations,
            "observed_at": self.observed_at,
            "source": self.source,
        }


def _btc(value: object) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(SATOSHI, rounding=ROUND_DOWN)
        if not amount.is_finite() or amount < 0:
            raise ValueError
        return amount
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BtcReserveError("invalid_rpc_btc_amount") from exc


class PythiaBtcReserveVerifier:
    """Fails closed when a dedicated reserve or confirmed UTXOs are unavailable."""

    def __init__(
        self,
        rpc: BitcoinRpc,
        *,
        reserve_address: str | None = None,
        min_confirmations: int = 6,
        now_fn=time.time,
    ) -> None:
        address = reserve_address or os.getenv("BTC_SETTLEMENT_RESERVE_ADDRESS", "").strip()
        if not address:
            raise BtcReserveError("btc_settlement_reserve_not_configured")
        if min_confirmations < 1:
            raise BtcReserveError("invalid_min_confirmations")
        self._rpc = rpc
        self._address = address
        self._min_confirmations = min_confirmations
        self._now_fn = now_fn

    def snapshot(self) -> BtcReserveSnapshot:
        try:
            raw = self._rpc.call("listunspent", [self._min_confirmations, 9_999_999, [self._address]])
        except Exception as exc:
            raise BtcReserveError("btc_reserve_rpc_unavailable") from exc
        if not isinstance(raw, list):
            raise BtcReserveError("invalid_btc_reserve_rpc_response")
        total = Decimal(0)
        count = 0
        for utxo in raw:
            if not isinstance(utxo, dict) or utxo.get("address") != self._address:
                continue
            try:
                confirmations = int(utxo.get("confirmations") or 0)
            except (TypeError, ValueError) as exc:
                raise BtcReserveError("invalid_rpc_utxo_confirmations") from exc
            if confirmations < self._min_confirmations:
                continue
            total += _btc(utxo.get("amount"))
            count += 1
        total = total.quantize(SATOSHI)
        return BtcReserveSnapshot(
            address=self._address,
            confirmed_btc=total,
            confirmed_sats=int((total * Decimal(100_000_000)).to_integral_value()),
            utxo_count=count,
            min_confirmations=self._min_confirmations,
            observed_at=int(self._now_fn()),
        )

"""Fail-closed, read-only THR settlement receipt gate for Earn #905.

Does not sign, broadcast, credit, move THC, or mark ledger entries settled.
A trusted adapter supplies independently observed finality and exact THR
transfer details. Browser-provided receipts and booleans are not authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

THR_UNIT = Decimal("0.000001")


class ThrReceiptError(ValueError):
    pass


@dataclass(frozen=True)
class ThrSettlementExpectation:
    reservation_id: str
    quote_id: str
    source_address: str
    destination_address: str
    gross_thr: str
    fee_thr: str
    net_thr: str


@dataclass(frozen=True)
class ObservedThrTransfer:
    tx_id: str
    source_address: str
    destination_address: str
    received_thr: str
    fee_thr: str
    confirmed: bool
    confirmation_ref: str
    quote_id: str
    reservation_id: str


class TrustedThrLedgerReader(Protocol):
    """Only an injected authoritative ledger/node adapter may implement this."""

    def lookup_confirmed_transfer(self, tx_id: str) -> ObservedThrTransfer:
        ...


def _exact(value: str, *, positive: bool) -> Decimal:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != number.quantize(THR_UNIT):
            raise ValueError
        if (number <= 0) if positive else (number < 0):
            raise ValueError
        return number
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ThrReceiptError("invalid_thr_precision_or_amount") from exc


def verify_thr_settlement_receipt(
    expected: ThrSettlementExpectation, tx_id: str, *, reader: TrustedThrLedgerReader
) -> ObservedThrTransfer:
    """Verify exact receipt. Caller must separately enforce device signatures,
    lock the reserved THC row and atomically record settlement after verification.
    """
    if not isinstance(tx_id, str) or not tx_id.strip() or len(tx_id) > 200:
        raise ThrReceiptError("thr_tx_id_required")
    if reader is None or not callable(getattr(reader, "lookup_confirmed_transfer", None)):
        raise ThrReceiptError("trusted_thr_reader_required")
    if not all((expected.reservation_id, expected.quote_id,
                expected.source_address, expected.destination_address)):
        raise ThrReceiptError("incomplete_thr_settlement_expectation")
    gross = _exact(expected.gross_thr, positive=True)
    fee = _exact(expected.fee_thr, positive=False)
    net = _exact(expected.net_thr, positive=True)
    if gross - fee != net:
        raise ThrReceiptError("thr_quote_arithmetic_mismatch")
    try:
        observed = reader.lookup_confirmed_transfer(tx_id)
    except Exception as exc:
        raise ThrReceiptError("thr_node_unavailable_reconcile") from exc
    if not isinstance(observed, ObservedThrTransfer):
        raise ThrReceiptError("untrusted_thr_receipt_format")
    if not observed.confirmed or not observed.confirmation_ref:
        raise ThrReceiptError("thr_not_confirmed_reconcile")
    if observed.tx_id != tx_id:
        raise ThrReceiptError("thr_tx_id_mismatch")
    if (observed.quote_id != expected.quote_id or
            observed.reservation_id != expected.reservation_id):
        raise ThrReceiptError("thr_receipt_binding_mismatch")
    if (observed.source_address != expected.source_address or
            observed.destination_address != expected.destination_address):
        raise ThrReceiptError("thr_wrong_transfer_participants")
    if (_exact(observed.received_thr, positive=True) != net or
            _exact(observed.fee_thr, positive=False) != fee):
        raise ThrReceiptError("thr_receipt_amount_mismatch")
    return observed

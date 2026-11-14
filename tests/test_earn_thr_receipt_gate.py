from dataclasses import replace
import pytest
from services.earn_thr_receipt_gate import (
    ThrReceiptError, ThrSettlementExpectation, ObservedThrTransfer,
    verify_thr_settlement_receipt,
)

EXP = ThrSettlementExpectation("res_1", "quote_1", "THRreserve", "THRrecipient",
                               "100.000000", "0.090000", "99.910000")
OBS = ObservedThrTransfer("tx_1", "THRreserve", "THRrecipient", "99.910000",
                          "0.090000", True, "node-proof:tx_1", "quote_1", "res_1")


class Reader:
    def __init__(self, observation=OBS):
        self.observation = observation
        self.calls = 0

    def lookup_confirmed_transfer(self, tx_id):
        self.calls += 1
        return self.observation


def test_verified_exact_receipt():
    assert verify_thr_settlement_receipt(EXP, "tx_1", reader=Reader()) == OBS


@pytest.mark.parametrize("change", [
    {"confirmed": False}, {"confirmation_ref": ""}, {"tx_id": "tx_2"},
    {"quote_id": "other"}, {"reservation_id": "other"},
    {"destination_address": "THRother"}, {"source_address": "THRother"},
    {"received_thr": "99.909999"}, {"fee_thr": "0.090001"},
    {"received_thr": "99.9100001"}, {"fee_thr": "NaN"},
])
def test_does_not_accept_invalid_receipt(change):
    with pytest.raises(ThrReceiptError):
        verify_thr_settlement_receipt(EXP, "tx_1", reader=Reader(replace(OBS, **change)))


@pytest.mark.parametrize("change", [
    {"gross_thr": "100.0000001"}, {"fee_thr": "0.0900001"},
    {"net_thr": "99.9100001"}, {"net_thr": "99.900000"},
])
def test_bad_quote_rejected_before_lookup(change):
    reader = Reader()
    with pytest.raises(ThrReceiptError):
        verify_thr_settlement_receipt(replace(EXP, **change), "tx_1", reader=reader)
    assert reader.calls == 0


def test_no_reader_or_tx_fails_closed():
    with pytest.raises(ThrReceiptError):
        verify_thr_settlement_receipt(EXP, "tx_1", reader=None)
    with pytest.raises(ThrReceiptError):
        verify_thr_settlement_receipt(EXP, "", reader=Reader())


def test_node_failure_requires_reconciliation():
    class BrokenReader:
        def lookup_confirmed_transfer(self, tx_id):
            raise TimeoutError("node offline")
    with pytest.raises(ThrReceiptError, match="thr_node_unavailable_reconcile"):
        verify_thr_settlement_receipt(EXP, "tx_1", reader=BrokenReader())

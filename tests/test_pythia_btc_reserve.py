from decimal import Decimal
import pytest

from services.pythia_btc_reserve import BtcReserveError, PythiaBtcReserveVerifier


ADDRESS = "bc1qsettlementreserve000000000000000000000000"


class FakeRpc:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else []
        self.error = error
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if self.error:
            raise self.error
        return self.result


def test_snapshot_counts_only_confirmed_utxos_for_exact_reserve():
    rpc = FakeRpc([
        {"address": ADDRESS, "amount": "0.10000000", "confirmations": 6},
        {"address": ADDRESS, "amount": "0.02000000", "confirmations": 9},
        {"address": ADDRESS, "amount": "1.00000000", "confirmations": 5},
        {"address": "bc1qother", "amount": "8.0", "confirmations": 100},
    ])
    snapshot = PythiaBtcReserveVerifier(
        rpc, reserve_address=ADDRESS, now_fn=lambda: 123,
    ).snapshot()
    assert snapshot.confirmed_btc == Decimal("0.12000000")
    assert snapshot.confirmed_sats == 12_000_000
    assert snapshot.utxo_count == 2
    assert rpc.calls == [("listunspent", [6, 9_999_999, [ADDRESS]])]


def test_rpc_failure_fails_closed():
    verifier = PythiaBtcReserveVerifier(
        FakeRpc(error=OSError("down")), reserve_address=ADDRESS,
    )
    with pytest.raises(BtcReserveError, match="btc_reserve_rpc_unavailable"):
        verifier.snapshot()


@pytest.mark.parametrize("result", [None, {}, "bad"])
def test_invalid_rpc_shape_fails_closed(result):
    verifier = PythiaBtcReserveVerifier(FakeRpc(result=result), reserve_address=ADDRESS)
    with pytest.raises(BtcReserveError, match="invalid_btc_reserve_rpc_response"):
        verifier.snapshot()


@pytest.mark.parametrize("amount", ["-1", "NaN", "not-a-number"])
def test_invalid_utxo_amount_fails_closed(amount):
    verifier = PythiaBtcReserveVerifier(
        FakeRpc([{"address": ADDRESS, "amount": amount, "confirmations": 7}]),
        reserve_address=ADDRESS,
    )
    with pytest.raises(BtcReserveError, match="invalid_rpc_btc_amount"):
        verifier.snapshot()


def test_dedicated_settlement_reserve_is_required():
    with pytest.raises(BtcReserveError, match="btc_settlement_reserve_not_configured"):
        PythiaBtcReserveVerifier(FakeRpc(), reserve_address="")


def test_no_float_conversion_in_source():
    import inspect
    import services.pythia_btc_reserve as module
    assert "float(" not in inspect.getsource(module)

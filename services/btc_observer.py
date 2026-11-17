"""Read-only Bitcoin deposit observer foundation.

No key derivation, signing, broadcasting, or balance crediting lives here.
Discovered transactions are normalized into durable txid:vout events.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import sqlite3
import time
from typing import Any, Mapping, Protocol

SATOSHIS_PER_BTC = Decimal("100000000")
SATOSHI = Decimal("0.00000001")

SEEN = "seen"
CONFIRMING = "confirming"
CONFIRMED = "confirmed"
CREDITED = "credited"
REORGED = "reorged"
VALID_STATES = frozenset({SEEN, CONFIRMING, CONFIRMED, CREDITED, REORGED})


class BtcObserverError(RuntimeError):
    pass


class BitcoinRpc(Protocol):
    def call(self, method: str, params: list[Any]) -> Any:
        ...


@dataclass(frozen=True)
class ObservedDeposit:
    event_id: str
    txid: str
    vout: int
    address: str
    owner_ref: str
    amount_sats: int
    confirmations: int
    block_hash: str | None
    block_height: int | None
    state: str
    first_seen_at: int
    last_seen_at: int
    credited_at: int | None
    requires_reconciliation: bool


def _hash256(value: object, error: str) -> str:
    result = str(value or "").strip().lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise BtcObserverError(error)
    return result


def _text(value: object, error: str, limit: int) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise BtcObserverError(error)
    return result


def _btc_to_sats(value: object) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BtcObserverError("invalid_btc_amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise BtcObserverError("invalid_btc_amount")
    quantized = amount.quantize(SATOSHI)
    if quantized != amount:
        raise BtcObserverError("btc_amount_below_satoshi_precision")
    return int((quantized * SATOSHIS_PER_BTC).to_integral_exact())


def _script_address(vout: Mapping[str, Any]) -> str | None:
    script = vout.get("scriptPubKey")
    if not isinstance(script, Mapping):
        return None
    direct = str(script.get("address") or "").strip()
    if direct:
        return direct
    addresses = script.get("addresses")
    if isinstance(addresses, list) and len(addresses) == 1:
        candidate = str(addresses[0] or "").strip()
        return candidate or None
    return None


def _state(confirmations: int, minimum: int) -> str:
    if confirmations <= 0:
        return SEEN
    if confirmations < minimum:
        return CONFIRMING
    return CONFIRMED


class BtcObserverStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS btc_observer_deposits (
                    event_id TEXT PRIMARY KEY,
                    txid TEXT NOT NULL,
                    vout INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    owner_ref TEXT NOT NULL,
                    amount_sats INTEGER NOT NULL,
                    confirmations INTEGER NOT NULL,
                    block_hash TEXT,
                    block_height INTEGER,
                    state TEXT NOT NULL,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    credited_at INTEGER,
                    requires_reconciliation INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(txid, vout)
                );
                CREATE INDEX IF NOT EXISTS idx_btc_observer_txid
                    ON btc_observer_deposits(txid);
                CREATE TABLE IF NOT EXISTS btc_observer_checkpoint (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    block_height INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    observed_at INTEGER NOT NULL
                );
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> ObservedDeposit:
        state = str(row["state"])
        if state not in VALID_STATES:
            raise BtcObserverError("invalid_persisted_observer_state")
        return ObservedDeposit(
            event_id=str(row["event_id"]),
            txid=str(row["txid"]),
            vout=int(row["vout"]),
            address=str(row["address"]),
            owner_ref=str(row["owner_ref"]),
            amount_sats=int(row["amount_sats"]),
            confirmations=int(row["confirmations"]),
            block_hash=str(row["block_hash"]) if row["block_hash"] else None,
            block_height=int(row["block_height"]) if row["block_height"] is not None else None,
            state=state,
            first_seen_at=int(row["first_seen_at"]),
            last_seen_at=int(row["last_seen_at"]),
            credited_at=int(row["credited_at"]) if row["credited_at"] is not None else None,
            requires_reconciliation=bool(row["requires_reconciliation"]),
        )

    def get(self, event_id: str) -> ObservedDeposit | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE event_id=?", (event_id,)
            ).fetchone()
        return self._row(row) if row else None

    def by_txid(self, txid: str) -> list[ObservedDeposit]:
        txid = _hash256(txid, "invalid_btc_txid")
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE txid=? ORDER BY vout", (txid,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def upsert(
        self, *, txid: str, vout: int, address: str, owner_ref: str,
        amount_sats: int, confirmations: int, block_hash: str | None,
        block_height: int | None, minimum_confirmations: int, observed_at: int,
    ) -> ObservedDeposit:
        event_id = f"{txid}:{vout}"
        with self._connect() as con:
            old = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE event_id=?", (event_id,)
            ).fetchone()
            next_state = _state(confirmations, minimum_confirmations)
            reconcile = 0

            if old:
                if (
                    str(old["address"]) != address
                    or str(old["owner_ref"]) != owner_ref
                    or int(old["amount_sats"]) != amount_sats
                ):
                    raise BtcObserverError("btc_observer_event_identity_conflict")

                previous_hash = str(old["block_hash"] or "")
                current_hash = str(block_hash or "")
                lost_finality = (
                    str(old["state"]) in (CONFIRMED, CREDITED)
                    and confirmations < minimum_confirmations
                )
                block_changed = bool(previous_hash and current_hash and previous_hash != current_hash)
                block_disappeared = bool(previous_hash and not current_hash)
                reconcile = int(old["requires_reconciliation"])

                if lost_finality or block_changed or block_disappeared:
                    next_state = REORGED
                    reconcile = 1
                elif reconcile:
                    next_state = REORGED
                elif str(old["state"]) == CREDITED:
                    next_state = CREDITED

                con.execute(
                    """UPDATE btc_observer_deposits
                       SET confirmations=?, block_hash=?, block_height=?, state=?,
                           last_seen_at=?, requires_reconciliation=?
                       WHERE event_id=?""",
                    (
                        confirmations, block_hash, block_height, next_state,
                        observed_at, reconcile, event_id,
                    ),
                )
            else:
                con.execute(
                    """INSERT INTO btc_observer_deposits
                       (event_id, txid, vout, address, owner_ref, amount_sats,
                        confirmations, block_hash, block_height, state,
                        first_seen_at, last_seen_at, credited_at,
                        requires_reconciliation)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,0)""",
                    (
                        event_id, txid, vout, address, owner_ref, amount_sats,
                        confirmations, block_hash, block_height, next_state,
                        observed_at, observed_at,
                    ),
                )

            row = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE event_id=?", (event_id,)
            ).fetchone()
        if row is None:
            raise BtcObserverError("btc_observer_state_write_failed")
        return self._row(row)

    def mark_credited(self, event_id: str, *, credited_at: int | None = None) -> ObservedDeposit:
        now = int(time.time()) if credited_at is None else int(credited_at)
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE event_id=?", (event_id,)
            ).fetchone()
            if not row:
                raise BtcObserverError("btc_observer_event_not_found")
            if int(row["requires_reconciliation"]):
                raise BtcObserverError("btc_observer_reconciliation_required")
            if str(row["state"]) == CREDITED:
                return self._row(row)
            if str(row["state"]) != CONFIRMED:
                raise BtcObserverError("btc_observer_event_not_final")
            con.execute(
                """UPDATE btc_observer_deposits
                   SET state=?, credited_at=?, last_seen_at=? WHERE event_id=?""",
                (CREDITED, now, now, event_id),
            )
            updated = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE event_id=?", (event_id,)
            ).fetchone()
        if updated is None:
            raise BtcObserverError("btc_observer_state_write_failed")
        return self._row(updated)

    def save_checkpoint(self, height: int, block_hash: str, *, observed_at: int) -> None:
        if height < 0:
            raise BtcObserverError("invalid_btc_block_height")
        block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        with self._connect() as con:
            con.execute(
                """INSERT INTO btc_observer_checkpoint
                   (singleton, block_height, block_hash, observed_at)
                   VALUES (1,?,?,?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     block_height=excluded.block_height,
                     block_hash=excluded.block_hash,
                     observed_at=excluded.observed_at""",
                (height, block_hash, observed_at),
            )

    def checkpoint(self) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT block_height, block_hash, observed_at "
                "FROM btc_observer_checkpoint WHERE singleton=1"
            ).fetchone()
        return dict(row) if row else None


class BtcObserver:
    def __init__(
        self, rpc: BitcoinRpc, store: BtcObserverStore,
        watched_addresses: Mapping[str, str], *,
        minimum_confirmations: int = 6, now_fn=time.time,
    ) -> None:
        if minimum_confirmations < 1:
            raise BtcObserverError("invalid_minimum_confirmations")
        watched = {
            _text(address, "invalid_btc_address", 128):
            _text(owner_ref, "invalid_owner_ref", 200)
            for address, owner_ref in watched_addresses.items()
        }
        if not watched:
            raise BtcObserverError("no_watched_btc_addresses")
        self.rpc = rpc
        self.store = store
        self.watched_addresses = watched
        self.minimum_confirmations = minimum_confirmations
        self.now_fn = now_fn

    def _block_height(self, block_hash: str | None) -> int | None:
        if not block_hash:
            return None
        header = self.rpc.call("getblockheader", [block_hash, True])
        if not isinstance(header, Mapping):
            raise BtcObserverError("invalid_btc_block_header")
        raw_height = header.get("height")
        if isinstance(raw_height, bool):
            raise BtcObserverError("invalid_btc_block_height")
        try:
            height = int(raw_height)
        except (TypeError, ValueError) as exc:
            raise BtcObserverError("invalid_btc_block_height") from exc
        if height < 0:
            raise BtcObserverError("invalid_btc_block_height")
        return height

    def observe_transaction(self, txid: str) -> list[ObservedDeposit]:
        txid = _hash256(txid, "invalid_btc_txid")
        raw = self.rpc.call("getrawtransaction", [txid, True])
        if not isinstance(raw, Mapping):
            raise BtcObserverError("btc_rpc_transaction_unavailable")
        if _hash256(raw.get("txid"), "invalid_btc_txid") != txid:
            raise BtcObserverError("btc_rpc_txid_mismatch")

        raw_conf = raw.get("confirmations", 0)
        if isinstance(raw_conf, bool):
            raise BtcObserverError("invalid_btc_confirmations")
        try:
            confirmations = max(0, int(raw_conf or 0))
        except (TypeError, ValueError) as exc:
            raise BtcObserverError("invalid_btc_confirmations") from exc

        block_hash = str(raw.get("blockhash") or "").strip() or None
        if block_hash:
            block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        block_height = self._block_height(block_hash)
        observed_at = int(self.now_fn())

        outputs = raw.get("vout")
        if not isinstance(outputs, list):
            raise BtcObserverError("invalid_btc_transaction_outputs")

        observed: list[ObservedDeposit] = []
        for fallback_n, output in enumerate(outputs):
            if not isinstance(output, Mapping):
                raise BtcObserverError("invalid_btc_transaction_output")
            address = _script_address(output)
            if not address or address not in self.watched_addresses:
                continue
            raw_n = output.get("n", fallback_n)
            if isinstance(raw_n, bool):
                raise BtcObserverError("invalid_btc_vout")
            try:
                vout = int(raw_n)
            except (TypeError, ValueError) as exc:
                raise BtcObserverError("invalid_btc_vout") from exc
            if vout < 0:
                raise BtcObserverError("invalid_btc_vout")

            observed.append(
                self.store.upsert(
                    txid=txid,
                    vout=vout,
                    address=address,
                    owner_ref=self.watched_addresses[address],
                    amount_sats=_btc_to_sats(output.get("value")),
                    confirmations=confirmations,
                    block_hash=block_hash,
                    block_height=block_height,
                    minimum_confirmations=self.minimum_confirmations,
                    observed_at=observed_at,
                )
            )
        return observed

    def checkpoint_tip(self) -> dict[str, Any]:
        raw_height = self.rpc.call("getblockcount", [])
        if isinstance(raw_height, bool):
            raise BtcObserverError("invalid_btc_block_height")
        try:
            height = int(raw_height)
        except (TypeError, ValueError) as exc:
            raise BtcObserverError("invalid_btc_block_height") from exc
        if height < 0:
            raise BtcObserverError("invalid_btc_block_height")
        block_hash = _hash256(
            self.rpc.call("getblockhash", [height]), "invalid_btc_block_hash"
        )
        observed_at = int(self.now_fn())
        self.store.save_checkpoint(height, block_hash, observed_at=observed_at)
        checkpoint = self.store.checkpoint()
        if checkpoint is None:
            raise BtcObserverError("btc_observer_checkpoint_write_failed")
        return checkpoint

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
DROPPED = "dropped"
VALID_STATES = frozenset({SEEN, CONFIRMING, CONFIRMED, CREDITED, REORGED, DROPPED})


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


def _strict_int(value: object, error: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BtcObserverError(error)
    if value < minimum:
        raise BtcObserverError(error)
    return value


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
                CREATE TABLE IF NOT EXISTS btc_observer_published_tip (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    block_height INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    published_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS btc_observer_reconciliation_checkpoint (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    range_start INTEGER NOT NULL,
                    target_height INTEGER NOT NULL,
                    last_verified_height INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS btc_observer_meta (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS btc_observer_diagnostics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    topic TEXT,
                    expected_sequence INTEGER,
                    observed_sequence INTEGER,
                    range_start INTEGER,
                    range_end INTEGER,
                    detail TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    detected_at INTEGER NOT NULL,
                    resolved_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_btc_observer_diagnostics_status
                    ON btc_observer_diagnostics(status, detected_at, id);
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

    def all_events(self) -> list[ObservedDeposit]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM btc_observer_deposits ORDER BY first_seen_at, event_id"
            ).fetchall()
        return [self._row(row) for row in rows]


    def mark_mempool_removed(
        self, txid: str, *, observed_at: int | None = None
    ) -> list[ObservedDeposit]:
        """Mark unconfirmed watched outputs as dropped after a ZMQ R event.

        Confirmed/credited rows are never changed by a mempool removal signal.
        A later reappearance of the same txid:vout can move DROPPED back to SEEN
        through the normal idempotent upsert path.
        """
        txid = _hash256(txid, "invalid_btc_txid")
        now = int(time.time()) if observed_at is None else int(observed_at)
        with self._connect() as con:
            con.execute(
                """UPDATE btc_observer_deposits
                   SET state=?, last_seen_at=?
                   WHERE txid=? AND block_hash IS NULL
                     AND state IN (?, ?)""",
                (DROPPED, now, txid, SEEN, DROPPED),
            )
            rows = con.execute(
                "SELECT * FROM btc_observer_deposits WHERE txid=? ORDER BY vout",
                (txid,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def next_sequence(self) -> int:
        """Atomically allocate a monotonic node-agent sequence number."""
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM btc_observer_meta WHERE key='node_agent_sequence'"
            ).fetchone()
            current = int(row["value"]) if row else 0
            next_value = current + 1
            con.execute(
                """INSERT INTO btc_observer_meta(key, value) VALUES('node_agent_sequence', ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (next_value,),
            )
        return next_value


    def set_meta_int(self, key: str, value: int) -> None:
        key = _text(key, "invalid_btc_observer_meta_key", 100)
        with self._connect() as con:
            con.execute(
                """INSERT INTO btc_observer_meta(key, value) VALUES(?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (key, int(value)),
            )

    def get_meta_int(self, key: str, default: int = 0) -> int:
        key = _text(key, "invalid_btc_observer_meta_key", 100)
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM btc_observer_meta WHERE key=?", (key,)
            ).fetchone()
        return int(row["value"]) if row else int(default)

    def record_diagnostic(
        self,
        category: str,
        *,
        topic: str | None = None,
        expected_sequence: int | None = None,
        observed_sequence: int | None = None,
        range_start: int | None = None,
        range_end: int | None = None,
        detail: str,
        detected_at: int | None = None,
    ) -> int:
        """Persist non-secret recovery evidence without changing safety flags."""
        category = _text(category, "invalid_btc_diagnostic_category", 100)
        topic = _text(topic, "invalid_btc_diagnostic_topic", 100) if topic else None
        detail = _text(detail, "invalid_btc_diagnostic_detail", 500)
        now = int(time.time()) if detected_at is None else int(detected_at)
        values = (expected_sequence, observed_sequence, range_start, range_end)
        if any(value is not None and (isinstance(value, bool) or value < 0) for value in values):
            raise BtcObserverError("invalid_btc_diagnostic_value")
        with self._connect() as con:
            cur = con.execute(
                """INSERT INTO btc_observer_diagnostics
                   (category, topic, expected_sequence, observed_sequence,
                    range_start, range_end, detail, status, detected_at)
                   VALUES (?,?,?,?,?,?,?,'open',?)""",
                (
                    category, topic, expected_sequence, observed_sequence,
                    range_start, range_end, detail, now,
                ),
            )
            return int(cur.lastrowid)

    def diagnostics(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as con:
            if status is None:
                rows = con.execute(
                    "SELECT * FROM btc_observer_diagnostics ORDER BY id"
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM btc_observer_diagnostics WHERE status=? ORDER BY id",
                    (status,),
                ).fetchall()
        return [dict(row) for row in rows]

    def save_published_tip(
        self, height: int, block_hash: str, sequence: int, *, published_at: int
    ) -> None:
        height = _strict_int(height, "invalid_btc_block_height")
        sequence = _strict_int(sequence, "invalid_btc_node_agent_sequence", minimum=1)
        block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        with self._connect() as con:
            con.execute(
                """INSERT INTO btc_observer_published_tip
                   (singleton, block_height, block_hash, sequence, published_at)
                   VALUES (1,?,?,?,?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     block_height=excluded.block_height,
                     block_hash=excluded.block_hash,
                     sequence=excluded.sequence,
                     published_at=excluded.published_at""",
                (height, block_hash, sequence, int(published_at)),
            )

    def published_tip(self) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT block_height, block_hash, sequence, published_at
                   FROM btc_observer_published_tip WHERE singleton=1"""
            ).fetchone()
        return dict(row) if row else None

    def begin_reconciliation(
        self, *, range_start: int, target_height: int, previous_height: int
    ) -> None:
        range_start = _strict_int(range_start, "invalid_btc_block_height")
        target_height = _strict_int(target_height, "invalid_btc_block_height")
        previous_height = _strict_int(previous_height, "invalid_btc_block_height")
        if range_start != previous_height + 1 or target_height < range_start:
            raise BtcObserverError("invalid_btc_reconciliation_range")
        now = int(time.time())
        with self._connect() as con:
            con.execute(
                """INSERT INTO btc_observer_reconciliation_checkpoint
                   (singleton, range_start, target_height, last_verified_height,
                    status, started_at, updated_at)
                   VALUES (1,?,?,?,'running',?,?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     range_start=excluded.range_start,
                     target_height=excluded.target_height,
                     last_verified_height=excluded.last_verified_height,
                     status='running',
                     started_at=excluded.started_at,
                     updated_at=excluded.updated_at""",
                (range_start, target_height, previous_height, now, now),
            )

    def reconciliation_checkpoint(self) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT range_start, target_height, last_verified_height,
                          status, started_at, updated_at
                   FROM btc_observer_reconciliation_checkpoint WHERE singleton=1"""
            ).fetchone()
        return dict(row) if row else None

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
                elif str(old["state"]) == DROPPED and confirmations <= 0:
                    next_state = SEEN

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
            global_flags = con.execute(
                """SELECT key, value FROM btc_observer_meta
                   WHERE key IN (
                     'observer_reconciliation_required','zmq_gap_detected',
                     'observer_unverified_history'
                   )"""
            ).fetchall()
            if any(int(flag["value"]) != 0 for flag in global_flags):
                raise BtcObserverError("btc_observer_global_reconciliation_required")
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
        height = _strict_int(height, "invalid_btc_block_height")
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

    def advance_checkpoint(
        self,
        height: int,
        block_hash: str,
        *,
        observed_at: int,
        expected_previous_height: int | None,
    ) -> None:
        """Atomically commit one fully scanned canonical block, never skipping."""
        height = _strict_int(height, "invalid_btc_block_height")
        block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        if expected_previous_height is not None:
            expected_previous_height = _strict_int(
                expected_previous_height, "invalid_btc_block_height"
            )
            if height != expected_previous_height + 1:
                raise BtcObserverError("btc_scan_checkpoint_non_contiguous")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT block_height, block_hash FROM btc_observer_checkpoint WHERE singleton=1"
            ).fetchone()
            if expected_previous_height is None:
                if row is not None:
                    raise BtcObserverError("btc_scan_checkpoint_concurrent_change")
            elif row is None or int(row["block_height"]) != expected_previous_height:
                raise BtcObserverError("btc_scan_checkpoint_concurrent_change")
            if row is not None and height <= int(row["block_height"]):
                raise BtcObserverError("btc_scan_checkpoint_not_advanced")
            con.execute(
                """INSERT INTO btc_observer_checkpoint
                   (singleton, block_height, block_hash, observed_at)
                   VALUES (1,?,?,?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     block_height=excluded.block_height,
                     block_hash=excluded.block_hash,
                     observed_at=excluded.observed_at""",
                (height, block_hash, int(observed_at)),
            )
            reconciliation = con.execute(
                """SELECT last_verified_height, target_height, status
                   FROM btc_observer_reconciliation_checkpoint WHERE singleton=1"""
            ).fetchone()
            if reconciliation is not None and str(reconciliation["status"]) == "running":
                if (
                    height != int(reconciliation["last_verified_height"]) + 1
                    or height > int(reconciliation["target_height"])
                ):
                    raise BtcObserverError("btc_reconciliation_checkpoint_conflict")
                status = (
                    "complete"
                    if height == int(reconciliation["target_height"])
                    else "running"
                )
                con.execute(
                    """UPDATE btc_observer_reconciliation_checkpoint
                       SET last_verified_height=?, status=?, updated_at=?
                       WHERE singleton=1""",
                    (height, status, int(observed_at)),
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
        return _strict_int(raw_height, "invalid_btc_block_height")

    def observe_decoded_transaction(
        self,
        raw: Mapping[str, Any],
        *,
        confirmations: int = 0,
        block_hash: str | None = None,
        block_height: int | None = None,
    ) -> list[ObservedDeposit]:
        """Validate the full transaction before persisting watched outputs."""
        if not isinstance(raw, Mapping):
            raise BtcObserverError("btc_rpc_transaction_unavailable")
        txid = _hash256(raw.get("txid"), "invalid_btc_txid")
        confirmations = _strict_int(confirmations, "invalid_btc_confirmations")

        if block_hash:
            block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        if block_height is not None:
            block_height = _strict_int(block_height, "invalid_btc_block_height")

        outputs = raw.get("vout")
        if not isinstance(outputs, list):
            raise BtcObserverError("invalid_btc_transaction_outputs")

        # Pre-validate every output first so a malformed later output can never
        # leave earlier watched outputs partially committed.
        prepared: list[tuple[int, str, str, int]] = []
        for output in outputs:
            if not isinstance(output, Mapping):
                raise BtcObserverError("invalid_btc_transaction_output")
            if "n" not in output:
                raise BtcObserverError("invalid_btc_vout")
            vout = _strict_int(output.get("n"), "invalid_btc_vout")
            address = _script_address(output)
            if not address or address not in self.watched_addresses:
                continue
            amount_sats = _btc_to_sats(output.get("value"))
            prepared.append(
                (vout, address, self.watched_addresses[address], amount_sats)
            )

        observed_at = int(self.now_fn())
        observed: list[ObservedDeposit] = []
        for vout, address, owner_ref, amount_sats in prepared:
            observed.append(
                self.store.upsert(
                    txid=txid,
                    vout=vout,
                    address=address,
                    owner_ref=owner_ref,
                    amount_sats=amount_sats,
                    confirmations=confirmations,
                    block_hash=block_hash,
                    block_height=block_height,
                    minimum_confirmations=self.minimum_confirmations,
                    observed_at=observed_at,
                )
            )
        return observed

    def observe_transaction(self, txid: str) -> list[ObservedDeposit]:
        """Legacy/read-only RPC lookup path for nodes with tx lookup available."""
        txid = _hash256(txid, "invalid_btc_txid")
        raw = self.rpc.call("getrawtransaction", [txid, True])
        if not isinstance(raw, Mapping):
            raise BtcObserverError("btc_rpc_transaction_unavailable")
        if _hash256(raw.get("txid"), "invalid_btc_txid") != txid:
            raise BtcObserverError("btc_rpc_txid_mismatch")

        raw_conf = raw.get("confirmations", 0)
        confirmations = _strict_int(raw_conf, "invalid_btc_confirmations")

        block_hash = str(raw.get("blockhash") or "").strip() or None
        if block_hash:
            block_hash = _hash256(block_hash, "invalid_btc_block_hash")
        block_height = self._block_height(block_hash)
        return self.observe_decoded_transaction(
            raw,
            confirmations=confirmations,
            block_hash=block_hash,
            block_height=block_height,
        )

    def observe_block(self, block: Mapping[str, Any]) -> list[ObservedDeposit]:
        """Scan a freshly announced decoded block (getblock verbosity=2)."""
        if not isinstance(block, Mapping):
            raise BtcObserverError("invalid_btc_block")
        block_hash = _hash256(block.get("hash"), "invalid_btc_block_hash")
        raw_height = block.get("height")
        height = _strict_int(raw_height, "invalid_btc_block_height")
        txs = block.get("tx")
        if not isinstance(txs, list):
            raise BtcObserverError("invalid_btc_block_transactions")

        observed: list[ObservedDeposit] = []
        for tx in txs:
            if not isinstance(tx, Mapping):
                raise BtcObserverError("invalid_btc_block_transaction")
            observed.extend(
                self.observe_decoded_transaction(
                    tx,
                    confirmations=1,
                    block_hash=block_hash,
                    block_height=height,
                )
            )
        return observed

    def reconcile_tip(self) -> list[ObservedDeposit]:
        """Recompute confirmations and detect reorgs using block-index RPC only."""
        raw_height = self.rpc.call("getblockcount", [])
        tip_height = _strict_int(raw_height, "invalid_btc_block_height")

        reconciled: list[ObservedDeposit] = []
        observed_at = int(self.now_fn())
        for event in self.store.all_events():
            if event.block_height is None or not event.block_hash:
                continue
            canonical_hash = _hash256(
                self.rpc.call("getblockhash", [event.block_height]),
                "invalid_btc_block_hash",
            )
            if canonical_hash != event.block_hash:
                reconciled.append(
                    self.store.upsert(
                        txid=event.txid,
                        vout=event.vout,
                        address=event.address,
                        owner_ref=event.owner_ref,
                        amount_sats=event.amount_sats,
                        confirmations=0,
                        block_hash=None,
                        block_height=None,
                        minimum_confirmations=self.minimum_confirmations,
                        observed_at=observed_at,
                    )
                )
                continue

            confirmations = max(1, tip_height - event.block_height + 1)
            reconciled.append(
                self.store.upsert(
                    txid=event.txid,
                    vout=event.vout,
                    address=event.address,
                    owner_ref=event.owner_ref,
                    amount_sats=event.amount_sats,
                    confirmations=confirmations,
                    block_hash=event.block_hash,
                    block_height=event.block_height,
                    minimum_confirmations=self.minimum_confirmations,
                    observed_at=observed_at,
                )
            )
        return reconciled

    def checkpoint_tip(self) -> dict[str, Any]:
        """Legacy unsafe API retained only to fail closed for old callers."""
        raise BtcObserverError("btc_checkpoint_tip_without_scan_forbidden")

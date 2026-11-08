"""TimeWall split attribution never creates unfunded referral tokens."""

import sqlite3
from decimal import Decimal

import pytest

from services.earn_account import EarnAccountStore
from services.earn_revenue_allocation import allocate_timewall_revenue


def test_exact_split_and_five_percent_is_part_of_platform_share():
    result = allocate_timewall_revenue('0.021')
    assert Decimal(result['player_share_usd']) == Decimal('0.01365')
    assert Decimal(result['referral_cap_usd']) == Decimal('0.00105')
    assert Decimal(result['platform_after_full_referrals_usd']) == Decimal('0.00630')
    assert (Decimal(result['player_share_usd']) + Decimal(result['referral_cap_usd'])
            + Decimal(result['platform_after_full_referrals_usd']) == Decimal('0.021'))


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '0', 'oops'])
def test_reject_invalid_revenue(value):
    with pytest.raises(ValueError):
        allocate_timewall_revenue(value)


def test_receipt_and_allocation_are_atomic_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv('TIMEWALL_THC_CONVERSION', '670')
    db = str(tmp_path / 'earn.db')
    store = EarnAccountStore(db, 'test-identity-key')
    user = store.register('split@example.com', 'password123')
    provider_id = store.provider_user_id(user['earn_user_id'], 'timewall')
    kwargs = dict(event_id='event-1', provider_user_id=provider_id,
                  revenue_raw='0.021', payload={})
    first, inserted = store.record_timewall_receipt(**kwargs)
    again, duplicate = store.record_timewall_receipt(**kwargs)
    assert inserted and not duplicate and first['thc_entry_id'] == again['thc_entry_id']
    with sqlite3.connect(db) as con:
        allocation = con.execute('SELECT player_share_usd, referral_cap_usd, '
            'platform_after_full_referrals_usd, credited_player_thc, status '
            'FROM earn_timewall_revenue_allocations WHERE event_id = ?', ('event-1',)).fetchone()
        assert allocation == ('0.01365', '0.00105', '0.00630', '14.000000',
                              'pending_reconciliation')
        assert con.execute('SELECT COUNT(*) FROM earn_timewall_revenue_allocations').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM thc_ledger WHERE source = ?',
                           ('timewall',)).fetchone()[0] == 1

"""Native Earn Account entry preserves existing Train-to-Earn and wallet navigation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = (ROOT / "thronos-wallet-app/src/screens/T2EDashboardScreen.tsx").read_text()
NAV = (ROOT / "thronos-wallet-app/App.tsx").read_text()


def test_native_earn_account_is_an_explicit_external_link():
    assert 'testID="nativeEarnAccountEntry"' in SCREEN
    assert 'Linking.openURL(`${CONFIG.API_URL}/earn`)' in SCREEN
    assert 'accessibilityRole="link"' in SCREEN
    assert 'Opens browser' in SCREEN


def test_existing_t2e_functions_and_wallet_routes_still_exist():
    for phrase in ("getT2EBalance(wallet.address)", "getT2EHistory(wallet.address, 20)",
                   "fetchDashboardData", "Start Earning", "Train to Earn"):
        assert phrase in SCREEN
    for route in ('name="Home"', 'name="T2E"', 'name="History"',
                  'name="Settings"'):
        assert route in NAV

"""Presentation-only Earn web tabs must preserve existing account/provider IDs."""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "templates/earn_beta.html").read_text()


def test_web_tabs_are_accessible_and_have_all_four_sections():
    for name in ("offers", "rewards", "community", "account"):
        assert f'id="earn-tab-{name}"' in HTML
        assert f'id="earn-panel-{name}"' in HTML
        assert f'data-earn-section="{name}"' in HTML
    assert 'role="tablist"' in HTML
    assert 'aria-selected="true"' in HTML
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in HTML
    assert '.earn-section-panel[hidden]' in HTML


def test_existing_provider_buttons_and_account_functionality_remain():
    for value in ("earn-surveys", "earn-timewall", "earn-bitcotasks",
                  "earn-pure", "earn-submit", "earn-balance-value",
                  "earn-pending-value", "earn-logout", "earn-referral",
                  "earn-leaderboard", "lb-staking", "earn-history",
                  "t2e-log-workout", "earn-frame", "earn-survey-close"):
        assert f'id="{value}"' in HTML
    assert "function earnAuthHeaders()" in HTML
    assert "async function refreshDashboard()" in HTML


def test_tab_view_does_not_touch_provider_auth_apis():
    assert "selectEarnSection('offers', false)" in HTML
    assert 'button.tabIndex = active ? 0 : -1' in HTML
    assert "panel.hidden = !active" in HTML
    assert "data-earn-section" in HTML

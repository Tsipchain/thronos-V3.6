from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"templates/earn_beta.html").read_text()
SVG=(ROOT/"static/img/thronos-earn-lockup.svg").read_text()

def test_earn_logo_is_local_and_has_correct_partners():
    assert 'src="/static/img/thronos-earn-lockup.svg"' in HTML
    assert 'ThronosLabs &amp; ENNCOM' in HTML
    assert 'POWERED BY ThronosLabs &amp; ENNCOM' in SVG
    assert 'viewBox="0 0 640 148"' in SVG

def test_wallet_and_provider_handlers_unmodified():
    for guard in ('id="earn-surveys"', 'id="earn-timewall"',
                  "window.ThronosEarnTabs.open(provider",
                  'id="earn-language"', 'id="earn-tab-advertise"'):
        assert guard in HTML

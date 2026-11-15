from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"templates/earn_beta.html").read_text()
PNG=ROOT/"static/img/THRONOS EARN.png"

def test_earn_logo_is_local_and_has_correct_partners():
    assert PNG.is_file()
    assert PNG.stat().st_size > 1000
    assert PNG.open("rb").read(8) == bytes.fromhex("89504e470d0a1a0a")
    assert 'src="/static/img/THRONOS%20EARN.png"' in HTML
    assert 'ThronosLabs &amp; ENCOMM' in HTML
    assert 'class="earn-product-logo"' in HTML

def test_language_toolbar_is_above_the_logo():
    start=HTML.index('<header class="earn-product-header"')
    end=HTML.index("</header>",start)
    head=HTML[start:end]
    assert head.index('id="earn-language"') < head.index('class="earn-product-logo"')

def test_wallet_and_provider_handlers_unmodified():
    for guard in ('id="earn-surveys"', 'id="earn-timewall"',
                  "window.ThronosEarnTabs.open(provider",
                  'id="earn-language"', 'id="earn-tab-advertise"'):
        assert guard in HTML

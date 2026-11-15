"""Ad creative preview must never activate billing, impressions, or serve events."""
from pathlib import Path

HTML=(Path(__file__).resolve().parents[1]/"templates/earn_beta.html").read_text()


def test_preview_uses_unfunded_local_only_dom():
    assert 'id="earn-ad-preview-button"' in HTML
    assert 'id="earn-ad-preview"' in HTML
    assert 'id="earn-ad-preview-headline"' in HTML
    assert 'id="earn-ad-preview-domain"' in HTML
    assert "const title = $('earn-ad-creative-title').value.trim()" in HTML
    assert "$('earn-ad-preview-headline').textContent = title" in HTML
    assert "$('earn-ad-preview-domain').textContent = destination.hostname" in HTML
    assert "if (destination.protocol !== 'https:'" in HTML
    assert "if (picture.protocol !== 'https:'" in HTML
    assert 'AD PREVIEW · Not live · No THC charge' in HTML


def test_original_creative_submission_and_tracking_unchanged():
    for marker in (
        "'/api/earn/ads/campaign/' + encodeURIComponent(campaignId) + '/creative/add'",
        "/api/earn/ads/impression", "/api/earn/ads/click",
        "showPromo(15)", "window.ThronosEarnTabs.open(provider",
        'id="earn-surveys"', 'id="earn-timewall"',
    ):
        assert marker in HTML
    assert 'type="button" data-earn-copy="previewCreative"' in HTML
    assert 'type="submit" data-earn-copy="submitCreative"' in HTML


def test_preview_in_all_supported_languages():
    for lang in ('en', 'gr', 'es', 'ja', 'ru'):
        assert f"    {lang}: {{" in HTML
    assert 'data-earn-copy="previewCreative"' in HTML
    assert 'data-earn-copy="previewDisclosure"' in HTML

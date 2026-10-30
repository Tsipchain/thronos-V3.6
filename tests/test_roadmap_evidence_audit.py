"""Regression checks for the evidence-led public roadmap.

These tests intentionally do not prove deployment. They prevent the template from
reintroducing unsupported 'completed' claims for gated money movement.
"""
from pathlib import Path


ROOT = Path(__file__).parent.parent
ROADMAP = ROOT / "templates" / "roadmap.html"
AUDIT = ROOT / "docs" / "THRONOS_ROADMAP_EVIDENCE_AUDIT_2026-10-30.md"


def test_public_roadmap_links_to_audit_and_uses_status_vocabulary():
    content = ROADMAP.read_text(encoding="utf-8")
    assert "THRONOS_ROADMAP_EVIDENCE_AUDIT_2026-10-30.md" in content
    for status in ("Verified", "Controlled pilot", "Draft / hardening", "Blocked by safety gate", "Planned"):
        assert status in content


def test_public_roadmap_does_not_claim_gated_money_movement_is_live():
    content = ROADMAP.read_text(encoding="utf-8").lower()
    forbidden = (
        "btc bridge withdrawals",
        "autonomous trading",
        "auto-receives fee",
        "100% ολ",
        "100% complete",
    )
    for phrase in forbidden:
        assert phrase not in content


def test_audit_defines_release_evidence_requirements():
    content = AUDIT.read_text(encoding="utf-8")
    for requirement in ("real transaction id", "chain confirmation", "durable idempotency", "reconciliation"):
        assert requirement in content.lower()

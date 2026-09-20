import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from risk import score_claim

GOOD_POLICY = {"active": True, "limit": 50000, "age_days": 400, "claims_last_90d": 0}

def test_clean_small_claim_is_auto_approved():
    claim = {"amount": 1200, "documents": ["photo", "police_report"],
             "days_since_incident": 1}
    r = score_claim(claim, GOOD_POLICY)
    assert r["decision"] == "AUTO_APPROVED"
    assert r["score"] == 0

def test_missing_document_blocks_auto_approval():
    claim = {"amount": 1200, "documents": ["photo"], "days_since_incident": 1}
    r = score_claim(claim, GOOD_POLICY)
    assert r["decision"] == "PENDING_REVIEW"
    assert any("missing" in x for x in r["reasons"])

def test_large_claim_goes_to_a_human():
    claim = {"amount": 9000, "documents": ["photo", "police_report"],
             "days_since_incident": 1}
    r = score_claim(claim, GOOD_POLICY)
    assert r["decision"] == "PENDING_REVIEW"

def test_inactive_policy_is_referred():
    claim = {"amount": 100, "documents": ["photo", "police_report"],
             "days_since_incident": 0}
    r = score_claim(claim, {"active": False, "limit": 1000,
                            "age_days": 400, "claims_last_90d": 0})
    assert r["decision"] == "REJECT_REFER"
    assert r["auto"] is False

def test_late_report_adds_points_but_may_still_pass():
    claim = {"amount": 800, "documents": ["photo", "police_report"],
             "days_since_incident": 10}
    r = score_claim(claim, GOOD_POLICY)
    assert r["score"] == 10
    assert r["decision"] == "AUTO_APPROVED"

def test_new_policy_with_recent_claim_is_reviewed():
    claim = {"amount": 800, "documents": ["photo", "police_report"],
             "days_since_incident": 1}
    r = score_claim(claim, {"active": True, "limit": 50000,
                            "age_days": 5, "claims_last_90d": 1})
    assert r["score"] == 35
    assert r["decision"] == "PENDING_REVIEW"

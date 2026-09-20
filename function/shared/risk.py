"""Claim triage rules for ClaimFlow.

Kept in one small module with no database or cloud imports so that it can be
unit tested on its own.  Every rule returns points; the total is the risk score.
A LOW score means the claim can be approved without a human.
"""

# Thresholds live here so they can be changed without touching the logic.
AUTO_APPROVE_MAX_AMOUNT = 5000.0     # ringgit
AUTO_APPROVE_MAX_SCORE = 30          # points
REQUIRED_DOCUMENTS = {"photo", "police_report"}

# How many points each situation adds to the risk score.
POINTS = {
    "missing_document": 40,
    "high_amount": 25,
    "recent_claim": 20,          # another claim on this policy in the last 90 days
    "policy_new": 15,            # policy less than 30 days old
    "late_report": 10,           # reported more than 7 days after the incident
    "amount_near_limit": 15,     # claim is within 5 % of the policy limit
}


def score_claim(claim: dict, policy: dict) -> dict:
    """Return the risk score, the reasons behind it, and the decision.

    claim  : {'amount': float, 'documents': set|list, 'days_since_incident': int}
    policy : {'active': bool, 'limit': float, 'age_days': int, 'claims_last_90d': int}
    """
    reasons = []
    score = 0

    if not policy.get("active", False):
        return {"score": 100, "reasons": ["policy is not active"],
                "decision": "REJECT_REFER", "auto": False}

    documents = set(claim.get("documents") or [])
    missing = REQUIRED_DOCUMENTS - documents
    if missing:
        score += POINTS["missing_document"]
        reasons.append("missing document(s): " + ", ".join(sorted(missing)))

    amount = float(claim.get("amount", 0))
    if amount > AUTO_APPROVE_MAX_AMOUNT:
        score += POINTS["high_amount"]
        reasons.append(f"amount {amount:.2f} above auto-approval limit "
                       f"{AUTO_APPROVE_MAX_AMOUNT:.2f}")

    limit = float(policy.get("limit", 0))
    if limit and amount >= limit * 0.95:
        score += POINTS["amount_near_limit"]
        reasons.append("amount is within 5 % of the policy limit")

    if int(policy.get("claims_last_90d", 0)) > 0:
        score += POINTS["recent_claim"]
        reasons.append("another claim on this policy in the last 90 days")

    if int(policy.get("age_days", 9999)) < 30:
        score += POINTS["policy_new"]
        reasons.append("policy is less than 30 days old")

    if int(claim.get("days_since_incident", 0)) > 7:
        score += POINTS["late_report"]
        reasons.append("reported more than 7 days after the incident")

    auto = (score <= AUTO_APPROVE_MAX_SCORE
            and amount <= AUTO_APPROVE_MAX_AMOUNT
            and not missing)

    return {
        "score": score,
        "reasons": reasons or ["no risk factors found"],
        "decision": "AUTO_APPROVED" if auto else "PENDING_REVIEW",
        "auto": auto,
    }

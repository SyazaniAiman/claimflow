"""ClaimFlow web portal and REST API.

Deliberately small.  Everything that makes a decision lives in risk.py so it can
be tested on its own; everything that touches the database lives in db.py.
"""
import os, uuid, datetime, logging
from flask import Flask, request, jsonify, render_template, abort, g

import db
from risk import score_claim

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

MAX_UPLOAD_MB = 10
ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}


# ---------- identity -------------------------------------------------------
def current_user():
    """In production the role comes from the validated Entra ID token.
    For local development only, X-Debug-Role lets you switch roles by hand.
    NEVER leave the debug branch enabled in production."""
    if os.environ.get("AUTH_MODE") == "local":
        return {"name": request.headers.get("X-Debug-User", "local.dev"),
                "role": request.headers.get("X-Debug-Role", "Adjuster")}
    principal = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME")
    roles = request.headers.get("X-MS-CLIENT-PRINCIPAL-ROLES", "")
    if not principal:
        abort(401)
    return {"name": principal, "role": roles.split(",")[0] if roles else "Claimant"}


def require(*roles):
    user = current_user()
    if user["role"] not in roles:
        logging.warning("denied: %s (%s) tried %s", user["name"], user["role"], request.path)
        abort(403)
    return user


# ---------- health ---------------------------------------------------------
@app.get("/health")
def health():
    """Container Apps calls this. Keep it cheap: no database call."""
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}, 200


@app.get("/ready")
def ready():
    """Deeper check used by smoke tests after a deployment."""
    try:
        db.query("SELECT 1 AS ok")
        return {"status": "ready"}, 200
    except Exception as exc:
        logging.exception("readiness failed")
        return {"status": "not-ready", "error": str(exc)}, 503


# ---------- pages ----------------------------------------------------------
@app.get("/")
def home():
    return render_template("index.html", user=current_user())


# ---------- API ------------------------------------------------------------
@app.post("/api/claims")
def create_claim():
    user = require("Claimant", "Adjuster", "Manager")
    body = request.get_json(force=True, silent=True) or {}

    for field in ("policy_no", "amount", "incident_date", "description"):
        if not body.get(field):
            return jsonify(error=f"'{field}' is required"), 400
    try:
        amount = float(body["amount"])
    except (TypeError, ValueError):
        return jsonify(error="'amount' must be a number"), 400
    if amount <= 0 or amount > 1_000_000:
        return jsonify(error="'amount' out of range"), 400

    policy = db.query(
        "SELECT policy_no, active, coverage_limit, age_days, claims_last_90d "
        "FROM policies WHERE policy_no = %s", (body["policy_no"],))
    if not policy:
        return jsonify(error="policy not found"), 404
    policy = policy[0]

    ref = "CLM-" + uuid.uuid4().hex[:10].upper()
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO claims (claim_ref, policy_no, claimant, amount, "
            "incident_date, description, status, risk_score) "
            "VALUES (%s,%s,%s,%s,%s,%s,'SUBMITTED',NULL)",
            (ref, body["policy_no"], user["name"], amount,
             body["incident_date"], body["description"][:1000]))
        db.audit(conn, user["name"], "CLAIM_CREATED", ref,
                 f"amount={amount}", request.remote_addr)

    return jsonify(claim_ref=ref, status="SUBMITTED"), 201


@app.get("/api/claims")
def list_claims():
    user = current_user()
    if user["role"] == "Claimant":
        rows = db.query("SELECT claim_ref, policy_no, amount, status, risk_score, "
                        "created_at FROM claims WHERE claimant = %s "
                        "ORDER BY created_at DESC", (user["name"],))
    elif user["role"] in ("Adjuster", "Manager", "Auditor"):
        rows = db.query("SELECT claim_ref, policy_no, amount, status, risk_score, "
                        "created_at FROM claims ORDER BY created_at DESC")
    else:
        abort(403)
    return jsonify(claims=rows, count=len(rows))


@app.get("/api/claims/<claim_ref>")
def get_claim(claim_ref):
    user = current_user()
    rows = db.query("SELECT * FROM claims WHERE claim_ref = %s", (claim_ref,))
    if not rows:
        abort(404)
    claim = rows[0]
    # A claimant may only ever see their own claim.  This check is on the
    # server, so hiding the link in the browser is not what protects it.
    if user["role"] == "Claimant" and claim["claimant"] != user["name"]:
        with db.connection() as conn:
            db.audit(conn, user["name"], "ACCESS_DENIED", claim_ref,
                     "attempted to view another claimant's claim",
                     request.remote_addr)
        abort(403)
    return jsonify(claim)


@app.post("/api/claims/<claim_ref>/decision")
def decide(claim_ref):
    user = require("Adjuster", "Manager")
    body = request.get_json(force=True, silent=True) or {}
    decision = body.get("decision")
    if decision not in ("APPROVED", "REJECTED"):
        return jsonify(error="decision must be APPROVED or REJECTED"), 400
    if not body.get("reason"):
        return jsonify(error="a reason is required for every decision"), 400

    rows = db.query("SELECT amount, status FROM claims WHERE claim_ref = %s",
                    (claim_ref,))
    if not rows:
        abort(404)
    amount = float(rows[0]["amount"])

    # Approval limit is enforced here, on the server, for every request.
    limit = float(os.environ.get("ADJUSTER_LIMIT", "5000"))
    if user["role"] == "Adjuster" and amount > limit:
        with db.connection() as conn:
            db.audit(conn, user["name"], "LIMIT_EXCEEDED", claim_ref,
                     f"amount={amount} limit={limit}", request.remote_addr)
        return jsonify(error=f"amount {amount:.2f} exceeds your limit "
                             f"of {limit:.2f}; refer to a Manager"), 403

    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE claims SET status=%s, decided_by=%s, "
                    "decided_at=SYSUTCDATETIME(), decision_reason=%s "
                    "WHERE claim_ref=%s",
                    (decision, user["name"], body["reason"][:500], claim_ref))
        db.audit(conn, user["name"], "DECISION_" + decision, claim_ref,
                 body["reason"][:500], request.remote_addr)

    return jsonify(claim_ref=claim_ref, status=decision)


@app.post("/api/claims/<claim_ref>/score")
def score_now(claim_ref):
    """Used by the smoke test and for a manual re-score.  The normal path is
    the serverless function, which calls the same rules."""
    require("Adjuster", "Manager")
    rows = db.query(
        "SELECT c.amount, c.incident_date, p.active, p.coverage_limit, "
        "p.age_days, p.claims_last_90d, "
        "(SELECT COUNT(*) FROM documents d WHERE d.claim_ref=c.claim_ref) AS doc_count "
        "FROM claims c JOIN policies p ON p.policy_no=c.policy_no "
        "WHERE c.claim_ref=%s", (claim_ref,))
    if not rows:
        abort(404)
    r = rows[0]
    docs = [d["doc_type"] for d in db.query(
        "SELECT doc_type FROM documents WHERE claim_ref=%s", (claim_ref,))]
    days = (datetime.date.today() - r["incident_date"]).days
    result = score_claim(
        {"amount": r["amount"], "documents": docs, "days_since_incident": days},
        {"active": bool(r["active"]), "limit": r["coverage_limit"],
         "age_days": r["age_days"], "claims_last_90d": r["claims_last_90d"]})
    return jsonify(result)


@app.errorhandler(403)
def forbidden(_):
    return jsonify(error="forbidden"), 403


@app.errorhandler(404)
def notfound(_):
    return jsonify(error="not found"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

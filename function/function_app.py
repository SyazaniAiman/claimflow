"""ClaimFlow serverless triage.

Runs when a document lands in the claim-documents container.  Reads the claim
and its policy, applies the same rules as the web app, writes the score and an
audit row, then stops.  Nothing runs and nothing is billed between claims.
"""
import datetime
import logging
import os
import sys

import azure.functions as func
import pymssql

sys.path.append(os.path.join(os.path.dirname(__file__), "shared"))
from risk import score_claim  # the identical rules used by the API

app = func.FunctionApp()


def _conn():
    return pymssql.connect(
        server=os.environ["SQL_SERVER"],
        user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASSWORD"],
        database=os.environ.get("SQL_DATABASE", "sqldb-claims"),
        tds_version="7.4", timeout=30)


@app.blob_trigger(arg_name="blob",
                  path="claim-documents/{claimRef}/{name}",
                  connection="AzureWebJobsStorage",
                  source=func.BlobSource.EVENT_GRID)
def TriageClaim(blob: func.InputStream):
    # The path is claim-documents/<claim_ref>/<timestamp>-<filename>
    parts = blob.name.split("/")
    claim_ref = parts[1] if len(parts) > 1 else None
    filename = parts[-1]
    logging.info("triage start ref=%s file=%s size=%s",
                 claim_ref, filename, blob.length)

    if not claim_ref:
        logging.warning("no claim reference in path, ignoring")
        return

    doc_type = ("police_report" if "police" in filename.lower()
                else "receipt" if "receipt" in filename.lower()
                else "photo")

    conn = _conn()
    try:
        cur = conn.cursor(as_dict=True)

        # Idempotency: event delivery is at-least-once on every platform, so
        # this function must tolerate running twice for the same blob.
        cur.execute("SELECT COUNT(*) AS n FROM documents WHERE blob_path=%s",
                    (blob.name,))
        if cur.fetchone()["n"] > 0:
            logging.info("already processed %s, nothing to do", blob.name)
            return

        cur.execute("INSERT INTO documents (claim_ref, doc_type, blob_path, "
                    "size_bytes) VALUES (%s,%s,%s,%s)",
                    (claim_ref, doc_type, blob.name, blob.length or 0))

        cur.execute(
            "SELECT c.amount, c.incident_date, p.active, p.coverage_limit, "
            "p.age_days, p.claims_last_90d "
            "FROM claims c JOIN policies p ON p.policy_no = c.policy_no "
            "WHERE c.claim_ref = %s", (claim_ref,))
        row = cur.fetchone()
        if not row:
            logging.warning("claim %s not found", claim_ref)
            conn.commit()
            return

        cur.execute("SELECT doc_type FROM documents WHERE claim_ref=%s",
                    (claim_ref,))
        docs = [r["doc_type"] for r in cur.fetchall()]

        days = (datetime.date.today() - row["incident_date"]).days
        result = score_claim(
            {"amount": float(row["amount"]), "documents": docs,
             "days_since_incident": days},
            {"active": bool(row["active"]), "limit": float(row["coverage_limit"]),
             "age_days": row["age_days"], "claims_last_90d": row["claims_last_90d"]})

        status = ("AUTO_APPROVED" if result["decision"] == "AUTO_APPROVED"
                  else "PENDING_REVIEW")
        reasons = "; ".join(result["reasons"])[:1000]

        cur.execute("UPDATE claims SET status=%s, risk_score=%s, risk_reasons=%s "
                    "WHERE claim_ref=%s", (status, result["score"], reasons, claim_ref))

        # Audit row committed in the same transaction as the change it records.
        cur.execute("INSERT INTO audit_log (actor, action, claim_ref, detail, "
                    "source_ip) VALUES (%s,%s,%s,%s,%s)",
                    ("system:TriageClaim", "AUTO_TRIAGE", claim_ref,
                     f"score={result['score']} status={status} :: {reasons}", None))
        conn.commit()
        logging.info("triage done ref=%s score=%s status=%s",
                     claim_ref, result["score"], status)
    except Exception:
        conn.rollback()
        logging.exception("triage failed for %s", claim_ref)
        raise          # let the platform retry, then dead-letter
    finally:
        conn.close()

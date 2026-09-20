#!/usr/bin/env python3
"""Nightly regulatory report.  Runs on the virtual machine at 02:00.

Deliberately the one self-managed component in ClaimFlow.  See Section 5.3.2
of the report for why it was kept.
"""
import os, datetime, logging
import pymssql
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

REPORT_CONTAINER = "reports"

def fetch_rows():
    conn = pymssql.connect(
        server=os.environ["SQL_SERVER"], user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASSWORD"],
        database=os.environ.get("SQL_DATABASE", "sqldb-claims"),
        tds_version="7.4")
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("""
            SELECT p.product,
                   COUNT(*)              AS claim_count,
                   SUM(c.amount)         AS total_amount,
                   AVG(CAST(c.risk_score AS FLOAT)) AS avg_risk,
                   SUM(CASE WHEN c.status='AUTO_APPROVED' THEN 1 ELSE 0 END) AS auto_approved
            FROM claims c JOIN policies p ON p.policy_no = c.policy_no
            WHERE CAST(c.created_at AS DATE) = CAST(DATEADD(day,-1,SYSUTCDATETIME()) AS DATE)
            GROUP BY p.product ORDER BY p.product""")
        return cur.fetchall()
    finally:
        conn.close()

def build_text(rows, day):
    lines = [f"ClaimFlow daily claims summary — {day}", "=" * 52, ""]
    if not rows:
        lines.append("No claims were submitted on this date.")
    else:
        lines.append(f"{'Product':<10}{'Claims':>8}{'Total (RM)':>14}"
                     f"{'Avg risk':>10}{'Auto':>7}")
        lines.append("-" * 52)
        for r in rows:
            lines.append(f"{r['product']:<10}{r['claim_count']:>8}"
                         f"{float(r['total_amount'] or 0):>14,.2f}"
                         f"{float(r['avg_risk'] or 0):>10.1f}"
                         f"{r['auto_approved']:>7}")
    lines += ["", f"Generated {datetime.datetime.utcnow():%Y-%m-%d %H:%M} UTC",
              "Synthetic data — not for regulatory submission."]
    return "\n".join(lines)

def main():
    day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    rows = fetch_rows()
    text = build_text(rows, day)
    name = f"daily-claims-{day}.txt"

    # Managed identity: the VM has no stored storage key to leak.
    cred = ManagedIdentityCredential()
    account = os.environ["STORAGE_ACCOUNT"]
    svc = BlobServiceClient(f"https://{account}.blob.core.windows.net",
                            credential=cred)
    svc.get_blob_client(REPORT_CONTAINER, name).upload_blob(
        text.encode("utf-8"), overwrite=True)
    logging.info("uploaded %s (%d bytes)", name, len(text))
    print(text)

if __name__ == "__main__":
    main()

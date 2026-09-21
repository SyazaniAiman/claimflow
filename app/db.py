"""Database helpers.  One place that knows how to talk to Azure SQL."""
import os
from contextlib import contextmanager

import pymssql


def _settings():
    return dict(
        server=os.environ["SQL_SERVER"],  # full Azure SQL host name
        user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASSWORD"],    # read from Key Vault at start-up
        database=os.environ.get("SQL_DATABASE", "sqldb-claims"),
    )

@contextmanager
def connection():
    """Open a connection, always close it, roll back if anything goes wrong."""
    conn = pymssql.connect(**_settings(), tds_version="7.4", timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql, params=()):
    with connection() as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(sql, params)
        return cur.fetchall()

def execute(sql, params=()):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.rowcount

def audit(conn, actor, action, claim_ref, detail, source_ip):
    """Write one audit row.  Takes an open connection so that the audit row and
    the change it describes are committed together, or not at all."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (actor, action, claim_ref, detail, source_ip) "
        "VALUES (%s, %s, %s, %s, %s)",
        (actor, action, claim_ref, detail, source_ip))

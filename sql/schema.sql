-- ClaimFlow database schema.  Run this once against sqldb-claims.

IF OBJECT_ID('audit_log','U')  IS NOT NULL DROP TABLE audit_log;
IF OBJECT_ID('documents','U')  IS NOT NULL DROP TABLE documents;
IF OBJECT_ID('claims','U')     IS NOT NULL DROP TABLE claims;
IF OBJECT_ID('policies','U')   IS NOT NULL DROP TABLE policies;

CREATE TABLE policies (
    policy_no        VARCHAR(20)   NOT NULL PRIMARY KEY,
    holder_name      NVARCHAR(120) NOT NULL,
    holder_ic        VARCHAR(20)   NULL,      -- masked for most roles, see below
    product          VARCHAR(30)   NOT NULL,  -- MOTOR or TRAVEL
    active           BIT           NOT NULL DEFAULT 1,
    coverage_limit   DECIMAL(12,2) NOT NULL,
    age_days         INT           NOT NULL DEFAULT 0,
    claims_last_90d  INT           NOT NULL DEFAULT 0,
    created_at       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE claims (
    claim_ref        VARCHAR(20)   NOT NULL PRIMARY KEY,
    policy_no        VARCHAR(20)   NOT NULL REFERENCES policies(policy_no),
    claimant         NVARCHAR(120) NOT NULL,
    amount           DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    incident_date    DATE          NOT NULL,
    description      NVARCHAR(1000) NULL,
    status           VARCHAR(20)   NOT NULL DEFAULT 'SUBMITTED',
    risk_score       INT           NULL,
    risk_reasons     NVARCHAR(1000) NULL,
    decided_by       NVARCHAR(120) NULL,
    decided_at       DATETIME2     NULL,
    decision_reason  NVARCHAR(500) NULL,
    created_at       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX ix_claims_status  ON claims(status, created_at DESC);
CREATE INDEX ix_claims_claimant ON claims(claimant, created_at DESC);

CREATE TABLE documents (
    id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    claim_ref   VARCHAR(20)   NOT NULL REFERENCES claims(claim_ref),
    doc_type    VARCHAR(30)   NOT NULL,   -- photo | police_report | receipt
    blob_path   NVARCHAR(400) NOT NULL,
    size_bytes  BIGINT        NOT NULL,
    uploaded_at DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX ix_documents_claim ON documents(claim_ref);

-- Append-only.  The application identity is granted INSERT and SELECT on this
-- table and nothing else, so a bug cannot quietly rewrite history.
CREATE TABLE audit_log (
    id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    at_utc      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    actor       NVARCHAR(120) NOT NULL,
    action      VARCHAR(40)   NOT NULL,
    claim_ref   VARCHAR(20)   NULL,
    detail      NVARCHAR(600) NULL,
    source_ip   VARCHAR(45)   NULL
);
CREATE INDEX ix_audit_claim ON audit_log(claim_ref, at_utc DESC);

-- Hide the identity card number from roles that do not need it.
ALTER TABLE policies
  ALTER COLUMN holder_ic ADD MASKED WITH (FUNCTION = 'partial(0,"XXXXXX-XX-",4)');
GO

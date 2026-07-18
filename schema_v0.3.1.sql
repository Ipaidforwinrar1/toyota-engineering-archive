
CREATE TABLE IF NOT EXISTS recovery_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    reference_id TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    source_url TEXT,
    target_path TEXT,
    outcome TEXT NOT NULL,
    http_status INTEGER,
    error_type TEXT,
    error_message TEXT,
    bytes_downloaded INTEGER,
    sha256 TEXT,
    elapsed_seconds REAL,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_recovery_attempts_reference
    ON recovery_attempts(reference_id);

CREATE INDEX IF NOT EXISTS idx_recovery_attempts_outcome
    ON recovery_attempts(outcome);

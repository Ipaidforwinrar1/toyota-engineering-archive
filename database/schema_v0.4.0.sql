PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS components (
    component_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    normalized_name TEXT NOT NULL UNIQUE,
    system_name TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS component_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id INTEGER NOT NULL,
    alias TEXT NOT NULL COLLATE NOCASE,
    normalized_alias TEXT NOT NULL UNIQUE,
    FOREIGN KEY (component_id) REFERENCES components(component_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_components (
    document_component_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_key TEXT NOT NULL,
    reference_id TEXT,
    component_id INTEGER NOT NULL,
    page_number INTEGER,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 1.0,
    extraction_method TEXT NOT NULL DEFAULT 'dictionary',
    first_context TEXT,
    extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_key, component_id, page_number),
    FOREIGN KEY (component_id) REFERENCES components(component_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS component_extraction_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    documents_seen INTEGER NOT NULL DEFAULT 0,
    documents_processed INTEGER NOT NULL DEFAULT 0,
    mentions_written INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_components_system ON components(system_name);
CREATE INDEX IF NOT EXISTS idx_alias_component ON component_aliases(component_id);
CREATE INDEX IF NOT EXISTS idx_doc_component_doc ON document_components(document_key);
CREATE INDEX IF NOT EXISTS idx_doc_component_ref ON document_components(reference_id);
CREATE INDEX IF NOT EXISTS idx_doc_component_component ON document_components(component_id);

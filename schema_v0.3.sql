PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id TEXT NOT NULL UNIQUE,
    document_uid TEXT NOT NULL UNIQUE,
    manufacturer TEXT,
    model_name TEXT,
    chassis_code TEXT,
    engine_code TEXT,
    transmission_code TEXT,
    model_year INTEGER,
    title TEXT NOT NULL,
    manual_type_original TEXT,
    manual_type_normalized TEXT,
    system_name TEXT,
    section_path TEXT,
    download_status TEXT,
    source_url TEXT,
    source_hash TEXT,
    original_local_path TEXT,
    resolved_local_path TEXT,
    file_exists INTEGER NOT NULL DEFAULT 0,
    pdf_valid INTEGER,
    size_bytes INTEGER,
    sha256 TEXT,
    download_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_title
    ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_manual
    ON documents(manual_type_normalized);
CREATE INDEX IF NOT EXISTS idx_documents_system
    ON documents(system_name);
CREATE INDEX IF NOT EXISTS idx_documents_engine
    ON documents(engine_code);
CREATE INDEX IF NOT EXISTS idx_documents_transmission
    ON documents(transmission_code);

CREATE TABLE IF NOT EXISTS pdf_analysis (
    document_id INTEGER PRIMARY KEY,
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    page_count INTEGER,
    metadata_title TEXT,
    metadata_author TEXT,
    metadata_subject TEXT,
    metadata_keywords TEXT,
    metadata_creator TEXT,
    metadata_producer TEXT,
    creation_date TEXT,
    modification_date TEXT,
    bookmark_count INTEGER,
    text_page_count INTEGER,
    image_only_page_count INTEGER,
    total_text_characters INTEGER,
    average_text_characters REAL,
    searchable_text INTEGER,
    needs_ocr INTEGER,
    encrypted INTEGER,
    extraction_error TEXT,
    analyzed_at TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_analysis_status
    ON pdf_analysis(analysis_status);
CREATE INDEX IF NOT EXISTS idx_analysis_needs_ocr
    ON pdf_analysis(needs_ocr);

CREATE TABLE IF NOT EXISTS pdf_bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    title TEXT NOT NULL,
    page_number INTEGER,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_document
    ON pdf_bookmarks(document_id);

CREATE TABLE IF NOT EXISTS pdf_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    text_content TEXT,
    text_characters INTEGER NOT NULL DEFAULT 0,
    has_text INTEGER NOT NULL DEFAULT 0,
    image_count INTEGER NOT NULL DEFAULT 0,
    width_points REAL,
    height_points REAL,
    rotation INTEGER,
    UNIQUE(document_id, page_number),
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pages_document
    ON pdf_pages(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS page_text_fts USING fts5(
    reference_id UNINDEXED,
    page_number UNINDEXED,
    title,
    section_path,
    text_content,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    command TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    succeeded INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

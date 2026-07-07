import sqlite3
import os

DB_PATH = os.environ.get("PROMPT_HUB_DB", "/app/data/prompt_hub.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    prompt_style TEXT NOT NULL,   -- 'commerce_en' | 'b2b_ru' | 'personal_ru'
    source_repo TEXT
);

CREATE TABLE IF NOT EXISTS rows_ (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id),
    sheet TEXT NOT NULL,             -- which xlsx sheet this came from
    name TEXT,                       -- current name / page / topic
    url TEXT,
    row_type TEXT,                   -- classification (STL/CNC, vendor hub, blog cluster, etc.)
    seo_title TEXT,
    h1 TEXT,
    meta_description TEXT,
    primary_keyword TEXT,
    secondary_keywords TEXT,
    lsi_keywords TEXT,
    faq_questions TEXT,
    extra_json TEXT,                 -- any extra fields per-site (vendor, geo, action, etc.)
    applied TEXT DEFAULT 'No',       -- No | Yes | Skipped
    date_applied TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_rows_site ON rows_(site_id);
CREATE INDEX IF NOT EXISTS idx_rows_applied ON rows_(applied);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

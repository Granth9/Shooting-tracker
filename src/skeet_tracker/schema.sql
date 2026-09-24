-- Database Schema: relational_skeet_schema.sql
-- Supports ISSF 25-target rounds, ISSF 2026 Finals (36), and drills.

CREATE TABLE IF NOT EXISTS rounds (
    round_id TEXT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL CHECK(event_type IN ('practice', 'qualification', 'final', 'drill')),
    format TEXT NOT NULL DEFAULT 'issf_25'
        CHECK(format IN ('issf_25', 'issf_final_36', 'drill')),
    drill_name TEXT,
    location TEXT,
    round_number INTEGER CHECK(round_number IS NULL OR round_number BETWEEN 1 AND 5),
    weather_condition TEXT,
    wind_speed_mph INTEGER CHECK(wind_speed_mph IS NULL OR wind_speed_mph >= 0),
    choke_used TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS shots (
    shot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT,
    sequence_order INTEGER NOT NULL CHECK(sequence_order BETWEEN 1 AND 200),
    station INTEGER CHECK(station BETWEEN 1 AND 8),
    target_house TEXT CHECK(target_house IN ('high', 'low')),
    is_double BOOLEAN NOT NULL,
    pair_position INTEGER CHECK(pair_position IN (0, 1, 2)),
    is_hit BOOLEAN NOT NULL,
    miss_direction TEXT CHECK(
        miss_direction IS NULL
        OR miss_direction IN ('behind', 'above', 'below', 'ahead', 'unknown')
    ),
    FOREIGN KEY(round_id) REFERENCES rounds(round_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shots_round_id ON shots(round_id);
CREATE INDEX IF NOT EXISTS idx_shots_station ON shots(station);
CREATE INDEX IF NOT EXISTS idx_rounds_event_type ON rounds(event_type);
CREATE INDEX IF NOT EXISTS idx_rounds_format ON rounds(format);

CREATE TABLE IF NOT EXISTS training_loads (
    load_date DATE PRIMARY KEY,
    workload REAL NOT NULL CHECK(workload >= 0),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS drill_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    blocks_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS competition_meets (
    meet_id TEXT PRIMARY KEY,
    event_date TEXT NOT NULL,
    date_precision TEXT NOT NULL DEFAULT 'year'
        CHECK(date_precision IN ('day', 'year')),
    year INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    level TEXT NOT NULL DEFAULT 'domestic'
        CHECK(level IN ('domestic', 'international')),
    qualification_score INTEGER,
    final_score INTEGER,
    selection_aggregate INTEGER,
    rounds_json TEXT,
    placing INTEGER,
    medal TEXT CHECK(medal IS NULL OR medal IN ('gold', 'silver', 'bronze')),
    source_url TEXT,
    source_label TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_competition_meets_year ON competition_meets(year);

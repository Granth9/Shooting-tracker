-- Database Schema: relational_skeet_schema.sql

CREATE TABLE IF NOT EXISTS rounds (
    round_id TEXT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT CHECK(event_type IN ('practice', 'qualification', 'final')),
    location TEXT,
    round_number INTEGER CHECK(round_number BETWEEN 1 AND 5),
    weather_condition TEXT,
    wind_speed_mph INTEGER CHECK(wind_speed_mph >= 0),
    choke_used TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS shots (
    shot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT,
    sequence_order INTEGER CHECK(sequence_order BETWEEN 1 AND 25),
    station INTEGER CHECK(station BETWEEN 1 AND 8),
    target_house TEXT CHECK(target_house IN ('high', 'low')),
    is_double BOOLEAN NOT NULL,
    pair_position INTEGER CHECK(pair_position IN (0, 1, 2)), -- 0=Single, 1=First Target, 2=Second Target
    is_hit BOOLEAN NOT NULL,
    miss_direction TEXT CHECK(miss_direction IN ('behind', 'above', 'below', 'ahead', 'unknown') OR miss_direction IS NULL),
    FOREIGN KEY(round_id) REFERENCES rounds(round_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shots_round_id ON shots(round_id);
CREATE INDEX IF NOT EXISTS idx_shots_station ON shots(station);

CREATE TABLE IF NOT EXISTS training_loads (
    load_date DATE PRIMARY KEY,
    workload REAL NOT NULL CHECK(workload >= 0),
    notes TEXT
);

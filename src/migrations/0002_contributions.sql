-- An accepted report as data for the next release (src/admin.js "Accept"): the change, the owner's public one-line
-- note and where the building is. No email and no name: a photo's credit stays on its report (photo_credit).
-- scripts/contributions.mjs pulls the unapplied rows into pipeline/contributions.csv and marks them applied.
CREATE TABLE contributions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports (id),
  kind TEXT NOT NULL,
  value TEXT NOT NULL DEFAULT '',
  public_note TEXT NOT NULL,
  replaces_register INTEGER NOT NULL DEFAULT 0,
  gid INTEGER,
  data_version TEXT,
  x REAL,
  z REAL,
  accepted_at TEXT NOT NULL,
  applied_version TEXT
);
CREATE INDEX contributions_applied ON contributions (applied_version);

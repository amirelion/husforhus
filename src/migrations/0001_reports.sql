-- Reports filed through the map's form (src/worker.js). No IP address is ever stored. The email is blanked by the
-- daily cron 12 months after a report closes (closed_at).
CREATE TABLE reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  building TEXT,
  message TEXT NOT NULL,
  email TEXT NOT NULL,
  lang TEXT NOT NULL,
  photo_key TEXT,
  photo_type TEXT,
  photo_credit TEXT,
  consent_own INTEGER NOT NULL DEFAULT 0,
  consent_licence INTEGER NOT NULL DEFAULT 0,
  photo_public INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  note TEXT NOT NULL DEFAULT '',
  issue_url TEXT,
  closed_at TEXT
);
CREATE INDEX reports_status ON reports (status);
CREATE INDEX reports_closed ON reports (closed_at);

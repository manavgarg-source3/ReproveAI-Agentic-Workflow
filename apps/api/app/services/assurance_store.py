"""Report-only writes; scientific data is read with a SQLite read-only snapshot."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from app.schemas.assurance import AssuranceReport


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def canonical_report(report):
    data = report.model_dump(mode="json") if isinstance(report, AssuranceReport) else dict(report)
    for key in ("report_id", "report_hash", "report_version", "generated_at", "created_at", "generated_by"):
        data.pop(key, None)
    return data


class ReportStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def read_snapshot(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            yield db
        finally:
            db.close()

    @contextmanager
    def reports(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS assurance_reports (
                  report_id TEXT PRIMARY KEY, research_case_id TEXT NOT NULL,
                  report_version INTEGER NOT NULL, report_hash TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL,
                  UNIQUE(research_case_id, report_version),
                  UNIQUE(research_case_id, report_hash)
                );
                CREATE TRIGGER IF NOT EXISTS assurance_reports_no_update
                  BEFORE UPDATE ON assurance_reports
                  BEGIN SELECT RAISE(ABORT, 'Assurance reports are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS assurance_reports_no_delete
                  BEFORE DELETE ON assurance_reports
                  BEGIN SELECT RAISE(ABORT, 'Assurance reports are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS assurance_reports_no_replace
                  BEFORE INSERT ON assurance_reports
                  WHEN EXISTS (SELECT 1 FROM assurance_reports WHERE report_id=NEW.report_id
                    OR (research_case_id=NEW.research_case_id AND report_version=NEW.report_version)
                    OR (research_case_id=NEW.research_case_id AND report_hash=NEW.report_hash))
                  BEGIN SELECT RAISE(ABORT, 'Assurance report identities are immutable'); END;
            ''')
            with db:
                yield db
        finally:
            db.close()

    def save(self, content, principal):
        content = canonical_report(content)
        report_hash = digest(content)
        with self.reports() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM assurance_reports WHERE research_case_id=? AND report_hash=?",
                             (content["research_case_id"], report_hash)).fetchone()
            if row:
                return self._decode(row[0])
            version = db.execute("SELECT COALESCE(MAX(report_version),0)+1 FROM assurance_reports WHERE research_case_id=?",
                                 (content["research_case_id"],)).fetchone()[0]
            now = datetime.now(timezone.utc)
            report = AssuranceReport(**content, report_id="REPORT-" + report_hash,
                                     report_hash=report_hash, report_version=version,
                                     generated_at=now, created_at=now, generated_by=principal)
            db.execute("INSERT INTO assurance_reports VALUES(?,?,?,?,?,?)",
                       (report.report_id, report.research_case_id, version, report_hash,
                        report.model_dump_json(), now.isoformat()))
            return report

    @staticmethod
    def _decode(payload):
        report = AssuranceReport.model_validate_json(payload)
        if digest(canonical_report(report)) != report.report_hash:
            raise ValueError("Stored report hash mismatch")
        return report

    def get(self, report_id):
        with self.reports() as db:
            row = db.execute("SELECT payload FROM assurance_reports WHERE report_id=?", (report_id,)).fetchone()
        return self._decode(row[0]) if row else None

    def list(self, case_id):
        with self.reports() as db:
            rows = db.execute("SELECT payload FROM assurance_reports WHERE research_case_id=? ORDER BY report_version DESC",
                              (case_id,)).fetchall()
        return [self._decode(row[0]) for row in rows]

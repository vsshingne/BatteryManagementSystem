import sqlite3
from pathlib import Path

from .models import Alert, Measurement, utcnow


class Database:
    def __init__(self, path: str):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS measurements (
              id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, source TEXT NOT NULL,
              voltage REAL, current REAL, temperature REAL, soc REAL,
              battery_status TEXT, charging INTEGER, operating_mode TEXT, runtime_minutes REAL);
            CREATE INDEX IF NOT EXISTS measurements_source_time ON measurements(source, timestamp);
            CREATE TABLE IF NOT EXISTS alerts (
              id INTEGER PRIMARY KEY, code TEXT NOT NULL, severity TEXT NOT NULL,
              description TEXT NOT NULL, timestamp TEXT NOT NULL, resolved_at TEXT,
              acknowledged INTEGER DEFAULT 0, source TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS alerts_source_time ON alerts(source, timestamp);
        ''')

    def store(self, reading: Measurement):
        fields = reading.model_dump(exclude={'id'})
        result = self.connection.execute(
            f"INSERT INTO measurements ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", list(fields.values()))
        self.connection.commit()
        reading.id = result.lastrowid

    def history(self, source: str, start: str | None = None, end: str | None = None, limit: int = 1000):
        clauses, args = ['source = ?'], [source]
        if start:
            clauses.append('timestamp >= ?'); args.append(start)
        if end:
            clauses.append('timestamp <= ?'); args.append(end)
        args.append(limit)
        rows = self.connection.execute(f"SELECT * FROM measurements WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC, id DESC LIMIT ?", args).fetchall()
        return [self.measurement(row) for row in reversed(rows)]

    @staticmethod
    def measurement(row):
        values = dict(row)
        values['charging'] = bool(values['charging'])
        return Measurement(**values)

    def latest(self, source: str):
        rows = self.history(source, limit=1)
        return rows[0] if rows else None

    def alert_history(self, source: str, limit: int = 500):
        return [Alert(**dict(row)) for row in self.connection.execute('SELECT * FROM alerts WHERE source=? ORDER BY id DESC LIMIT ?', (source, limit))]

    def update_alerts(self, source: str, active: dict[str, tuple[str, str]]):
        rows = self.connection.execute('SELECT id, code FROM alerts WHERE source=? AND resolved_at IS NULL', (source,)).fetchall()
        codes = {r['code'] for r in rows}
        now = utcnow()
        for row in rows:
            if row['code'] not in active:
                self.connection.execute('UPDATE alerts SET resolved_at=? WHERE id=?', (now, row['id']))
        for code, (severity, description) in active.items():
            if code not in codes:
                self.connection.execute('INSERT INTO alerts(code,severity,description,timestamp,source) VALUES(?,?,?,?,?)', (code, severity, description, now, source))
        self.connection.commit()

    def acknowledge(self, alert_id: int, source: str) -> bool:
        cursor = self.connection.execute('UPDATE alerts SET acknowledged=1 WHERE id=? AND source=?', (alert_id, source))
        self.connection.commit()
        return cursor.rowcount > 0

    def close(self):
        self.connection.close()

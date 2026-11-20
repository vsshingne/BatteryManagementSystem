import sqlite3
from pathlib import Path
from .models import Alert, Measurement, utcnow

class Database:
    def __init__(self, path: str):
        if path != ':memory:': Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, source TEXT NOT NULL,
            voltage REAL, current REAL, temperature REAL, soc REAL, battery_status TEXT,
            charging INTEGER, operating_mode TEXT, runtime_minutes REAL);
          CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY, code TEXT NOT NULL, severity TEXT NOT NULL,
            description TEXT NOT NULL, timestamp TEXT NOT NULL, resolved_at TEXT,
            acknowledged INTEGER DEFAULT 0, source TEXT NOT NULL);
        ''')
        self._add_column('measurements', 'battery_id', "TEXT NOT NULL DEFAULT 'BATTERY_1'")
        self._add_column('measurements', 'device_id', 'TEXT')
        self._add_column('alerts', 'battery_id', "TEXT DEFAULT 'BATTERY_1'")
        # Prior system had exactly one monitored battery, so its events map to Battery 1.
        self.connection.execute("UPDATE alerts SET battery_id='BATTERY_1' WHERE battery_id IS NULL")
        self.connection.commit()
        self.connection.executescript('''
          CREATE INDEX IF NOT EXISTS measurements_battery_source_time ON measurements(battery_id,source,timestamp);
          CREATE INDEX IF NOT EXISTS alerts_battery_source_time ON alerts(battery_id,source,timestamp);
        ''')

    def _add_column(self, table, column, definition):
        columns = {r['name'] for r in self.connection.execute(f'PRAGMA table_info({table})')}
        if column not in columns:
            self.connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
            self.connection.commit()

    def store(self, reading: Measurement):
        fields = reading.model_dump(exclude={'id'})
        result = self.connection.execute(f"INSERT INTO measurements ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", list(fields.values()))
        self.connection.commit(); reading.id = result.lastrowid

    @staticmethod
    def measurement(row):
        values = dict(row); values['charging'] = bool(values['charging'])
        if 'battery_id' not in values: values['battery_id'] = 'BATTERY_1'
        if 'device_id' not in values: values['device_id'] = None
        return Measurement(**values)

    def history(self, source, start=None, end=None, limit=1000, battery_id=None):
        clauses, args = ['source = ?'], [source]
        if battery_id: clauses.append('battery_id = ?'); args.append(battery_id)
        if start: clauses.append('timestamp >= ?'); args.append(start)
        if end: clauses.append('timestamp <= ?'); args.append(end)
        args.append(limit)
        rows = self.connection.execute(f"SELECT * FROM measurements WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC,id DESC LIMIT ?", args).fetchall()
        return [self.measurement(r) for r in reversed(rows)]

    def latest(self, source, battery_id=None):
        rows = self.history(source, limit=1, battery_id=battery_id)
        return rows[0] if rows else None

    def latest_all(self, source):
        return {bid: self.latest(source, bid) for bid in ('BATTERY_1','BATTERY_2')}

    def alert_history(self, source, limit=500, battery_id=None):
        sql, args = 'SELECT * FROM alerts WHERE source=?', [source]
        if battery_id: sql += ' AND battery_id=?'; args.append(battery_id)
        sql += ' ORDER BY id DESC LIMIT ?'; args.append(limit)
        return [Alert(**dict(row)) for row in self.connection.execute(sql, args)]

    def update_alerts(self, source, battery_id, active):
        rows = self.connection.execute('SELECT id,code FROM alerts WHERE source=? AND battery_id=? AND resolved_at IS NULL', (source,battery_id)).fetchall()
        codes = {r['code'] for r in rows}; now = utcnow()
        for row in rows:
            if row['code'] not in active: self.connection.execute('UPDATE alerts SET resolved_at=? WHERE id=?',(now,row['id']))
        for code,(severity,description) in active.items():
            if code not in codes: self.connection.execute('INSERT INTO alerts(code,severity,description,timestamp,source,battery_id) VALUES(?,?,?,?,?,?)',(code,severity,description,now,source,battery_id))
        self.connection.commit()

    def acknowledge(self, alert_id, source):
        cur=self.connection.execute('UPDATE alerts SET acknowledged=1 WHERE id=? AND source=?',(alert_id,source)); self.connection.commit(); return cur.rowcount>0
    def close(self): self.connection.close()

"""SQLite transaction boundary for locally configured API integrations."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import app_runtime
from data_credentials import _crypt


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


class Store:
    def __init__(self, path=None):
        self.path = path

    @contextmanager
    def transaction(self):
        path = self.path or Path(app_runtime.settings()["storage_dir"]) / "private/integrations.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, isolation_level=None, timeout=8)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS integrations(id TEXT PRIMARY KEY, spec TEXT NOT NULL, key BLOB);
            CREATE TABLE IF NOT EXISTS usage(id TEXT REFERENCES integrations ON DELETE CASCADE, day TEXT, n INTEGER NOT NULL, PRIMARY KEY(id,day));
            CREATE TABLE IF NOT EXISTS approvals(token TEXT PRIMARY KEY, id TEXT REFERENCES integrations ON DELETE CASCADE,
                revision INTEGER NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL, expires REAL NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM approvals WHERE expires <= ?", (time.time(),))
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def protect(spec, key):
        if not isinstance(key, str) or not 1 <= len(key) <= 2048 or any(not 33 <= ord(c) <= 126 for c in key):
            raise ValueError("Clave inválida.")
        return _crypt(packed([spec["id"], spec["base_url"], key]).encode())

    @staticmethod
    def reveal(spec, blob):
        if not blob:
            raise ValueError("Guardá la clave de esta integración.")
        ident, base, key = json.loads(_crypt(blob, decrypt=True))
        if (ident, base) != (spec["id"], spec["base_url"]):
            raise ValueError("La clave no corresponde a esta integración.")
        return key

    @staticmethod
    def get(db, ident):
        row = db.execute("SELECT spec,key FROM integrations WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("Integración inexistente.")
        return json.loads(row["spec"]), row["key"]

    @staticmethod
    def used(db, ident):
        row = db.execute("SELECT n FROM usage WHERE id=? AND day=date('now')", (ident,)).fetchone()
        return row[0] if row else 0

    def reserve(self, db, spec):
        if self.used(db, spec["id"]) >= spec["daily_limit"]:
            raise ValueError("La integración alcanzó su límite diario.")
        db.execute("""INSERT INTO usage VALUES (?,date('now'),1)
                    ON CONFLICT(id,day) DO UPDATE SET n=n+1""", (spec["id"],))

    @staticmethod
    def request_approval(db, spec, payload):
        count = db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        if count >= 100:
            raise ValueError("Hay demasiadas aprobaciones pendientes.")
        token = uuid.uuid4().hex
        expires = int(time.time()) + 300
        # Request arguments may contain personal information. Protect them at rest.
        sealed = _crypt(packed(payload).encode())
        db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?)", (token, spec["id"], spec["revision"], sealed, digest(payload), expires))
        return token, expires


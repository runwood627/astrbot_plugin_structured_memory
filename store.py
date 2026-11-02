"""Scoped structured facts; no model-generated SQL is executed."""
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class FactStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY, scope TEXT NOT NULL, user_id TEXT NOT NULL,
                category TEXT NOT NULL, attribute TEXT NOT NULL, value TEXT NOT NULL,
                source_message_id TEXT NOT NULL, source_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'active')""")
            db.execute("CREATE INDEX IF NOT EXISTS fact_lookup ON facts(scope,user_id,category,status)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(facts)")}
            if "supersedes_id" not in columns:
                db.execute("ALTER TABLE facts ADD COLUMN supersedes_id INTEGER")
            if "expires_on" not in columns:
                db.execute("ALTER TABLE facts ADD COLUMN expires_on TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, scope TEXT NOT NULL, author_id TEXT NOT NULL,
                title TEXT NOT NULL, description TEXT NOT NULL,
                occurred_at TEXT NOT NULL, source_message_id TEXT NOT NULL,
                source_text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("CREATE INDEX IF NOT EXISTS event_lookup ON events(scope,occurred_at)")
            db.execute("CREATE TABLE IF NOT EXISTS profile_sharing (scope TEXT NOT NULL, user_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope,user_id))")
            db.execute("CREATE TABLE IF NOT EXISTS cross_session_consent (platform_id TEXT NOT NULL, user_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(platform_id,user_id))")
            event_columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "status" not in event_columns:
                db.execute("ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "supersedes_id" not in event_columns:
                db.execute("ALTER TABLE events ADD COLUMN supersedes_id INTEGER")

    def save(self, scope, user_id, category, attribute, value, source_id, source_text, *, certainty="confirmed", expires_on=""):
        scope, user_id = str(scope or '').strip(), str(user_id or '').strip()
        category, attribute, value = str(category or '').strip(), str(attribute or '').strip()[:80], str(value or '').strip()[:300]
        source_id, source_text = str(source_id or '')[:100], str(source_text or '').strip()[:1000]
        if not all((scope, user_id, category, attribute, value, source_text)):
            raise ValueError("missing required fact fields")
        if category not in {"称呼", "偏好", "性格", "关系", "个人信息", "其他"}:
            raise ValueError("unsupported category")
        if certainty not in {"confirmed", "unconfirmed"}:
            raise ValueError("unsupported certainty")
        expiry = date.fromisoformat(expires_on).isoformat() if expires_on else None
        status = "active" if certainty == "confirmed" else "unconfirmed"
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT id FROM facts WHERE scope=? AND user_id=? AND category=? AND attribute=? AND value=? AND status=? AND expires_on IS ?", (scope,user_id,category,attribute,value,status,expiry)).fetchone()
            if row:
                return row[0]
            return db.execute("INSERT INTO facts(scope,user_id,category,attribute,value,source_message_id,source_text,status,expires_on) VALUES(?,?,?,?,?,?,?,?,?)", (scope,user_id,category,attribute,value,source_id,source_text,status,expiry)).lastrowid

    def search(self, scope, user_id, category="", attribute="", limit=20, confirmed_only=False):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT id,category,attribute,value,source_text,created_at,status,expires_on FROM facts WHERE scope=? AND user_id=? AND status IN ('active','unconfirmed') AND (?=0 OR status='active') AND (expires_on IS NULL OR expires_on>=?) AND (?='' OR category=?) AND (?='' OR attribute=?) ORDER BY id DESC LIMIT ?", (scope,user_id,int(confirmed_only),today,category,category,attribute,attribute,limit)).fetchall()

    def list_facts(self, scope, user_id, limit=50):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT id,category,attribute,value,source_text,created_at,status,expires_on,source_message_id FROM facts WHERE scope=? AND user_id=? ORDER BY id DESC LIMIT ?", (scope,user_id,limit)).fetchall()

    def set_profile_sharing(self, scope, user_id, enabled):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO profile_sharing(scope,user_id,enabled) VALUES(?,?,?) ON CONFLICT(scope,user_id) DO UPDATE SET enabled=excluded.enabled", (scope,user_id,int(enabled)))

    def shared_profile(self, scope, target_user_id, limit=20):
        """Return only opted-in, confirmed, non-sensitive facts in this session."""
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        with closing(sqlite3.connect(self.path)) as db:
            permission = db.execute("SELECT enabled FROM profile_sharing WHERE scope=? AND user_id=?", (scope,target_user_id)).fetchone()
            if not permission or not permission[0]:
                return []
            return db.execute("SELECT category,attribute,value FROM facts WHERE scope=? AND user_id=? AND status='active' AND category IN ('称呼','偏好','性格') AND (expires_on IS NULL OR expires_on>=?) ORDER BY id DESC LIMIT ?", (scope,target_user_id,today,limit)).fetchall()

    def set_cross_session(self, platform_id, user_id, enabled):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO cross_session_consent VALUES(?,?,?) ON CONFLICT(platform_id,user_id) DO UPDATE SET enabled=excluded.enabled", (platform_id,user_id,int(enabled)))

    def own_cross_session(self, platform_id, user_id, current_scope, limit=8):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        escaped = platform_id.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        with closing(sqlite3.connect(self.path)) as db:
            consent = db.execute("SELECT enabled FROM cross_session_consent WHERE platform_id=? AND user_id=?", (platform_id,user_id)).fetchone()
            if not consent or not consent[0]:
                return []
            return db.execute("SELECT category,attribute,value FROM facts WHERE scope LIKE ? ESCAPE '\\' AND scope<>? AND user_id=? AND status='active' AND category IN ('称呼','偏好','性格') AND (expires_on IS NULL OR expires_on>=?) ORDER BY id DESC LIMIT ?", (escaped+':%',current_scope,user_id,today,limit)).fetchall()

    def forget(self, scope, user_id, fact_id):
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT id,supersedes_id FROM facts WHERE scope=? AND user_id=? AND id=?", (scope,user_id,fact_id)).fetchone()
            if not row:
                return 0
            root = row[0]
            while row[1] is not None:
                row = db.execute("SELECT id,supersedes_id FROM facts WHERE scope=? AND user_id=? AND id=?", (scope,user_id,row[1])).fetchone()
                if not row:
                    break
                root = row[0]
            db.execute("WITH RECURSIVE history(id) AS (SELECT id FROM facts WHERE scope=? AND user_id=? AND id=? UNION SELECT f.id FROM facts f JOIN history h ON f.supersedes_id=h.id WHERE f.scope=? AND f.user_id=?) DELETE FROM facts WHERE scope=? AND user_id=? AND id IN (SELECT id FROM history)", (scope,user_id,root,scope,user_id,scope,user_id))
            return 1

    def correct(self, scope, user_id, fact_id, value, source_id, source_text):
        if not value.strip() or not source_text.strip():
            raise ValueError("correction requires value and evidence")
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute("SELECT category,attribute,expires_on FROM facts WHERE scope=? AND user_id=? AND id=? AND status IN ('active','unconfirmed')", (scope,user_id,fact_id)).fetchone()
            if not old:
                return None
            db.execute("UPDATE facts SET status='superseded' WHERE scope=? AND user_id=? AND id=?", (scope,user_id,fact_id))
            return db.execute("INSERT INTO facts(scope,user_id,category,attribute,value,source_message_id,source_text,supersedes_id,expires_on) VALUES(?,?,?,?,?,?,?,?,?)", (scope,user_id,old[0],old[1],value.strip()[:300],source_id[:100],source_text[:1000],fact_id,old[2])).lastrowid

    def save_event(self, scope, author_id, title, description, occurred_at, source_id, source_text):
        from datetime import datetime
        if not all((scope, author_id, title.strip(), description.strip(), source_text.strip())):
            raise ValueError("event and evidence must not be empty")
        date = datetime.strptime(occurred_at, "%Y-%m-%d").date().isoformat()
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute("INSERT INTO events(scope,author_id,title,description,occurred_at,source_message_id,source_text) VALUES(?,?,?,?,?,?,?)", (scope,author_id,title[:120],description[:500],date,source_id[:100],source_text[:1000])).lastrowid

    def search_events(self, scope, keyword="", start="", end="", limit=20):
        keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT id,title,description,occurred_at,source_text FROM events WHERE scope=? AND status='active' AND (?='' OR occurred_at>=?) AND (?='' OR occurred_at<=?) AND (?='' OR title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\') ORDER BY occurred_at DESC,id DESC LIMIT ?", (scope,start,start,end,end,keyword,f'%{keyword}%',f'%{keyword}%',limit)).fetchall()

    def forget_event(self, scope, author_id, event_id):
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT id,supersedes_id FROM events WHERE scope=? AND author_id=? AND id=?", (scope,author_id,event_id)).fetchone()
            if not row:
                return 0
            root = row[0]
            while row[1] is not None:
                row = db.execute("SELECT id,supersedes_id FROM events WHERE scope=? AND author_id=? AND id=?", (scope,author_id,row[1])).fetchone()
                if not row:
                    break
                root = row[0]
            db.execute("WITH RECURSIVE history(id) AS (SELECT id FROM events WHERE scope=? AND author_id=? AND id=? UNION SELECT e.id FROM events e JOIN history h ON e.supersedes_id=h.id WHERE e.scope=? AND e.author_id=?) DELETE FROM events WHERE scope=? AND author_id=? AND id IN (SELECT id FROM history)", (scope,author_id,root,scope,author_id,scope,author_id))
            return 1

    def correct_event(self, scope, author_id, event_id, title, description, occurred_at, source_id, source_text):
        if not all((title.strip(), description.strip(), source_text.strip())):
            raise ValueError("event correction and evidence are required")
        event_date = date.fromisoformat(occurred_at).isoformat()
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute("SELECT id FROM events WHERE scope=? AND author_id=? AND id=? AND status='active'", (scope,author_id,event_id)).fetchone()
            if not old:
                return None
            db.execute("UPDATE events SET status='superseded' WHERE scope=? AND author_id=? AND id=?", (scope,author_id,event_id))
            return db.execute("INSERT INTO events(scope,author_id,title,description,occurred_at,source_message_id,source_text,supersedes_id) VALUES(?,?,?,?,?,?,?,?)", (scope,author_id,title[:120],description[:500],event_date,source_id[:100],source_text[:1000],event_id)).lastrowid

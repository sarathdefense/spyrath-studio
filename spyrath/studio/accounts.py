from __future__ import annotations
import hashlib, hmac, os, sqlite3
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class User:
    user_id: str
    display_name: str

class AccountStore:
    """Small SQLite account/project ownership registry for Studio deployments."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, api_key_hash TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS project_owners(project_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id));''')
    def _db(self): return sqlite3.connect(self.path)
    @staticmethod
    def _hash(key: str) -> str: return hashlib.sha256(key.encode()).hexdigest()
    def ensure_user(self, user_id: str, display_name: str, api_key: str) -> User:
        if not user_id or not api_key: raise ValueError('user_id and api_key are required')
        with self._db() as db:
            db.execute('INSERT INTO users(user_id,display_name,api_key_hash) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name, api_key_hash=excluded.api_key_hash',(user_id,display_name,self._hash(api_key)))
        return User(user_id, display_name)
    def authenticate(self, api_key: str | None) -> User | None:
        if not api_key: return None
        digest=self._hash(api_key)
        with self._db() as db: row=db.execute('SELECT user_id,display_name,api_key_hash FROM users WHERE api_key_hash=?',(digest,)).fetchone()
        if not row or not hmac.compare_digest(row[2],digest): return None
        return User(row[0],row[1])
    def claim_project(self, project_id: str, user_id: str) -> None:
        with self._db() as db: db.execute('INSERT INTO project_owners(project_id,user_id) VALUES(?,?)',(project_id,user_id))
    def owns(self, project_id: str, user_id: str) -> bool:
        with self._db() as db: row=db.execute('SELECT 1 FROM project_owners WHERE project_id=? AND user_id=?',(project_id,user_id)).fetchone()
        return bool(row)
    def projects_for(self,user_id:str)->set[str]:
        with self._db() as db: return {r[0] for r in db.execute('SELECT project_id FROM project_owners WHERE user_id=?',(user_id,))}

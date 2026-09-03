from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Plan:
    plan_id: str
    name: str
    max_projects: int
    monthly_production_starts: int

    def as_dict(self):
        return asdict(self)


BETA_PLAN = Plan("beta", "Spyrath Beta", 10, 50)


class UsageStore:
    """Durable, dependency-free usage ledger used for beta limits and billing telemetry."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions(
              user_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL, event_type TEXT NOT NULL,
              project_id TEXT, created_at TEXT NOT NULL
            );
            """)

    def _db(self):
        return sqlite3.connect(self.path)

    def plan_for(self, user_id: str) -> Plan:
        with self._db() as db:
            row = db.execute("SELECT plan_id FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
        return BETA_PLAN if not row or row[0] == "beta" else BETA_PLAN

    def set_beta(self, user_id: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO subscriptions(user_id,plan_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET plan_id=excluded.plan_id", (user_id, "beta"))

    def record(self, user_id: str, event_type: str, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute("INSERT INTO usage_events(user_id,event_type,project_id,created_at) VALUES(?,?,?,?)", (user_id, event_type, project_id, now))

    def monthly_count(self, user_id: str, event_type: str) -> int:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._db() as db:
            row = db.execute("SELECT COUNT(*) FROM usage_events WHERE user_id=? AND event_type=? AND substr(created_at,1,7)=?", (user_id, event_type, month)).fetchone()
        return int(row[0])

    def summary(self, user_id: str, project_count: int) -> dict:
        plan = self.plan_for(user_id)
        starts = self.monthly_count(user_id, "production_start")
        return {
            "plan": plan.as_dict(),
            "projects": {"used": project_count, "limit": plan.max_projects},
            "production_starts": {"used": starts, "limit": plan.monthly_production_starts},
        }

    def require_project_capacity(self, user_id: str, project_count: int) -> None:
        plan = self.plan_for(user_id)
        if project_count >= plan.max_projects:
            raise PermissionError(f"Project limit reached for {plan.name} ({plan.max_projects})")

    def require_production_capacity(self, user_id: str) -> None:
        plan = self.plan_for(user_id)
        if self.monthly_count(user_id, "production_start") >= plan.monthly_production_starts:
            raise PermissionError(f"Monthly production limit reached for {plan.name} ({plan.monthly_production_starts})")

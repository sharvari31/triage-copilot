"""SQLite store for triage results awaiting human approval."""
import asyncio
import sqlite3
from datetime import datetime, timezone

from .schemas import TriageResult


class AlreadyDecided(Exception):
    pass


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS triages (
                    triage_id TEXT PRIMARY KEY, ticket_id TEXT, status TEXT, result_json TEXT,
                    decision TEXT, reviewer TEXT, final_reply TEXT, assignee TEXT, decided_at TEXT)"""
            )

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def _save(self, r: TriageResult):
        with self._conn() as c:
            c.execute(
                "INSERT INTO triages (triage_id, ticket_id, status, result_json, assignee) VALUES (?,?,?,?,?)",
                (r.triage_id, r.ticket_id, r.status, r.model_dump_json(), r.assignee),
            )

    def _get(self, triage_id: str) -> TriageResult | None:
        with self._conn() as c:
            row = c.execute("SELECT result_json FROM triages WHERE triage_id=?", (triage_id,)).fetchone()
        return TriageResult.model_validate_json(row[0]) if row else None

    def _decide(self, triage_id, decision, reviewer, final_reply, assignee):
        with self._conn() as c:
            cur = c.execute(
                """UPDATE triages SET decision=?, reviewer=?, final_reply=?, assignee=?, decided_at=?
                   WHERE triage_id=? AND decision IS NULL""",
                (decision, reviewer, final_reply, assignee, datetime.now(timezone.utc).isoformat(), triage_id),
            )
            if cur.rowcount == 0:
                raise AlreadyDecided(triage_id)

    async def save(self, r: TriageResult):
        await asyncio.to_thread(self._save, r)

    async def get(self, triage_id: str) -> TriageResult | None:
        return await asyncio.to_thread(self._get, triage_id)

    async def decide(self, triage_id, decision, reviewer, final_reply, assignee):
        await asyncio.to_thread(self._decide, triage_id, decision, reviewer, final_reply, assignee)

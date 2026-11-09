"""Requests the assistant hands over to the store's staff, kept in a local JSON Lines file."""
import json
from pathlib import Path

from emporio_agent.config import TICKETS_FILE
from emporio_agent.store_hours import store_now


class TicketLog:
    def __init__(self, path: Path = TICKETS_FILE) -> None:
        self._path = path

    def open(self, kind: str, summary: str, contact: str, order_id: int | None = None) -> str:
        ticket_id = f"EM-{self._count() + 1:05d}"
        record = {
            "id": ticket_id,
            "opened_at": store_now().isoformat(timespec="seconds"),
            "kind": kind,
            "summary": summary,
            "contact": contact,
            "order_id": order_id,
        }
        with open(self._path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return ticket_id

    def _count(self) -> int:
        if not self._path.exists():
            return 0
        with open(self._path, encoding="utf-8") as file:
            return sum(1 for _ in file)

"""Library members and borrowing limits."""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TIER_LIMITS = {
    "student": 3,
    "faculty": 8,
    "public": 2,
}

LOAN_DAYS = {"student": 14, "faculty": 28, "public": 14}


@dataclass
class Member:
    member_id: str
    name: str
    tier: str
    joined: date

    def years(self, today: date) -> float:
        return round((today - self.joined).days / 365.25, 1)


class MemberDirectory:
    def __init__(self, members: list[Member]):
        self._by_id = {m.member_id: m for m in members}

    def find(self, member_id: str) -> Member | None:
        return self._by_id.get(member_id.strip().upper())

    def all(self) -> list[Member]:
        return sorted(self._by_id.values(), key=lambda m: m.name)

    def by_tier(self, tier: str) -> list[Member]:
        return [m for m in self.all() if m.tier == tier]


def load_members(path: Path) -> MemberDirectory:
    raw = json.loads(path.read_text(encoding="utf-8"))
    members = [
        Member(
            member_id=r["member_id"].strip().upper(),
            name=r["name"].strip(),
            tier=r["tier"].strip().lower(),
            joined=date.fromisoformat(r["joined"]),
        )
        for r in raw
    ]
    return MemberDirectory(members)


def can_borrow(member: Member, active: int) -> bool:
    return active < TIER_LIMITS[member.tier]


def loan_days(member: Member) -> int:
    return LOAN_DAYS.get(member.tier, 14)

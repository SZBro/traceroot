"""Read a project file."""
import json
import re
from datetime import date
from pathlib import Path

from .model import Project, Task

UNIT_DAYS = {"d": 1, "w": 5}

DURATION_RE = re.compile(r"^\s*(\d+)\s*([a-z])\s*$")


class ProjectFileError(ValueError):
    pass


def parse_duration(text: str) -> int:
    m = DURATION_RE.match(text.lower())
    if not m:
        raise ProjectFileError(f"bad duration {text!r}")
    amount, unit = int(m.group(1)), m.group(2)
    return amount * UNIT_DAYS[unit]


def parse_date(text: str) -> date:
    return date.fromisoformat(text.strip())


def task_from_dict(raw: dict) -> Task:
    return Task(
        id=raw["id"].strip().upper(),
        name=raw["name"].strip(),
        duration=parse_duration(raw["duration"]),
        owner=raw.get("owner", "unassigned").strip().lower(),
        priority=int(raw.get("priority", 3)),
        deps=[d.strip().upper() for d in raw.get("deps", [])],
    )


def load_project(path: Path) -> Project:
    data = json.loads(path.read_text(encoding="utf-8"))
    project = Project(name=data["name"], start=parse_date(data["start"]))
    for raw in data["tasks"]:
        project.add(task_from_dict(raw))
    bad = project.unknown_deps()
    if bad:
        raise ProjectFileError("unknown dependencies: " + ", ".join(f"{a}->{b}" for a, b in bad))
    return project

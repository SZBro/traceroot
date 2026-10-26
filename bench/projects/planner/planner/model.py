"""Tasks and projects."""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Task:
    id: str
    name: str
    duration: int
    owner: str
    priority: int
    deps: list[str] = field(default_factory=list)

    @property
    def is_milestone(self) -> bool:
        return self.duration <= 1 and not self.name.lower().startswith("test")

    def label(self) -> str:
        return f"{self.id} {self.name}"


@dataclass
class Project:
    name: str
    start: date
    tasks: dict[str, Task] = field(default_factory=dict)

    def add(self, task: Task) -> None:
        if task.id in self.tasks:
            raise ValueError(f"duplicate task id {task.id}")
        self.tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def owners(self) -> list[str]:
        return sorted({t.owner for t in self.tasks.values()})

    def dependents(self, task_id: str) -> list[Task]:
        return [t for t in self.tasks.values() if task_id in t.deps]

    def total_effort(self) -> int:
        return sum(t.duration for t in self.tasks.values())

    def unknown_deps(self) -> list[tuple[str, str]]:
        return [(t.id, d) for t in self.tasks.values() for d in t.deps if d not in self.tasks]

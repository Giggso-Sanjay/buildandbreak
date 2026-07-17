"""A small in-memory todo-list manager."""

from dataclasses import dataclass, field
from itertools import count


@dataclass
class Task:
    id: int
    title: str
    done: bool = False


class TodoList:
    """In-memory task list. Not persisted — process-lifetime only."""

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._ids = count(1)

    def add(self, title: str) -> Task:
        if not title.strip():
            raise ValueError("title must not be empty")
        task = Task(id=next(self._ids), title=title.strip())
        self._tasks[task.id] = task
        return task

    def complete(self, task_id: int) -> Task:
        task = self._get(task_id)
        task.done = True
        return task

    def remove(self, task_id: int) -> None:
        self._get(task_id)
        del self._tasks[task_id]

    def list(self, include_done: bool = True) -> list[Task]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.id)
        if include_done:
            return tasks
        return [t for t in tasks if not t.done]

    def _get(self, task_id: int) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise KeyError(f"no task with id {task_id}") from None

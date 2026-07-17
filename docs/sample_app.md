# sample_app — TodoList

A minimal, in-memory todo-list manager. It exists to exercise Raven
Enterprise's design/signoff telemetry pipeline end to end; it is **not**
part of the main product.

## What it is

`sample_app` provides a single small module, `sample_app/todo.py`, with two
public types:

- `Task` — a dataclass representing one todo item.
- `TodoList` — a container that adds, completes, removes, and lists tasks.

State lives entirely in memory. Nothing is persisted to disk or any store,
and each `TodoList` instance is independent. When the process exits, all
tasks are gone.

## API

### `Task`

```python
@dataclass
class Task:
    id: int        # unique, monotonically increasing within one TodoList
    title: str     # non-empty, whitespace-stripped
    done: bool = False
```

### `TodoList`

Construct with no arguments: `todo = TodoList()`. Each instance keeps its own
task store and its own id counter starting at `1`.

| Method | Signature | Returns | Raises |
| --- | --- | --- | --- |
| `add` | `add(title: str) -> Task` | the created `Task` (id assigned, `done=False`) | `ValueError` if `title` is empty or whitespace-only |
| `complete` | `complete(task_id: int) -> Task` | the same stored `Task`, now `done=True` | `KeyError` if no task has that id |
| `remove` | `remove(task_id: int) -> None` | `None` | `KeyError` if no task has that id |
| `list` | `list(include_done: bool = True) -> list[Task]` | tasks sorted by id; when `include_done=False`, only tasks where `done` is `False` | — |

Notes:

- `add` strips leading/trailing whitespace from `title` before storing it.
- `complete` is idempotent — completing an already-done task is safe and
  simply returns it still marked done.
- `complete` returns the same object held in the list, so mutating the
  returned `Task` mutates the stored one.
- The id counter is never reused; removing a task does not free its id.

## Usage

```python
from sample_app.todo import TodoList

todo = TodoList()

t1 = todo.add("Buy milk")
t2 = todo.add("Walk dog")
todo.add("  Code review  ")     # stored as "Code review"

todo.complete(t2.id)            # mark "Walk dog" done

todo.list()                     # -> [Task(1, "Buy milk"), Task(2, "Walk dog", done=True), Task(3, "Code review")]
todo.list(include_done=False)   # -> [Task(1, "Buy milk"), Task(3, "Code review")]

todo.remove(t1.id)              # drop "Buy milk"
todo.list()                     # -> [Task(2, "Walk dog", done=True), Task(3, "Code review")]
```

## Scope and caveats

- In-memory only, non-persisted, process-lifetime-only.
- Not thread-safe; intended for single-threaded, illustrative use.
- Built purely as a sample workload for Raven's design/signoff telemetry
  pipeline — do not depend on it from production code.

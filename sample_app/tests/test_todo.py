"""Pytest coverage for TodoList."""

import pytest
from sample_app.todo import Task, TodoList


class TestTodoListAdd:
    """Test TodoList.add() method."""

    def test_add_single_task(self) -> None:
        """Adding a single task returns a Task with incremented id."""
        todo = TodoList()
        task = todo.add("Buy milk")
        assert task.id == 1
        assert task.title == "Buy milk"
        assert task.done is False

    def test_add_multiple_tasks(self) -> None:
        """Multiple adds produce tasks with sequential ids."""
        todo = TodoList()
        task1 = todo.add("First")
        task2 = todo.add("Second")
        task3 = todo.add("Third")
        assert task1.id == 1
        assert task2.id == 2
        assert task3.id == 3

    def test_add_strips_whitespace(self) -> None:
        """Title is stripped of leading/trailing whitespace."""
        todo = TodoList()
        task = todo.add("  Task with spaces  ")
        assert task.title == "Task with spaces"

    def test_add_empty_title_raises_valueerror(self) -> None:
        """Adding a task with empty title raises ValueError."""
        todo = TodoList()
        with pytest.raises(ValueError, match="title must not be empty"):
            todo.add("")

    def test_add_whitespace_only_raises_valueerror(self) -> None:
        """Adding a task with only whitespace raises ValueError."""
        todo = TodoList()
        with pytest.raises(ValueError, match="title must not be empty"):
            todo.add("   ")
        with pytest.raises(ValueError, match="title must not be empty"):
            todo.add("\t\n")


class TestTodoListComplete:
    """Test TodoList.complete() method."""

    def test_complete_task(self) -> None:
        """Completing a task sets done=True."""
        todo = TodoList()
        task = todo.add("Fix bug")
        assert task.done is False
        completed = todo.complete(task.id)
        assert completed.done is True
        assert completed.id == task.id
        assert completed.title == task.title

    def test_complete_unknown_id_raises_keyerror(self) -> None:
        """Completing a non-existent task raises KeyError."""
        todo = TodoList()
        with pytest.raises(KeyError, match="no task with id 99"):
            todo.complete(99)

    def test_complete_returns_same_task_instance(self) -> None:
        """Complete returns the same Task object from storage."""
        todo = TodoList()
        task = todo.add("Verify")
        completed = todo.complete(task.id)
        assert completed is task  # same object


class TestTodoListRemove:
    """Test TodoList.remove() method."""

    def test_remove_task(self) -> None:
        """Removing a task deletes it from the list."""
        todo = TodoList()
        task = todo.add("Delete me")
        task_id = task.id
        todo.remove(task_id)
        with pytest.raises(KeyError):
            todo.complete(task_id)

    def test_remove_unknown_id_raises_keyerror(self) -> None:
        """Removing a non-existent task raises KeyError."""
        todo = TodoList()
        with pytest.raises(KeyError, match="no task with id 42"):
            todo.remove(42)

    def test_remove_returns_none(self) -> None:
        """Remove returns None."""
        todo = TodoList()
        task = todo.add("Task")
        result = todo.remove(task.id)
        assert result is None


class TestTodoListList:
    """Test TodoList.list() method."""

    def test_list_empty(self) -> None:
        """Listing an empty TodoList returns empty list."""
        todo = TodoList()
        tasks = todo.list()
        assert tasks == []

    def test_list_returns_all_tasks_by_default(self) -> None:
        """list() includes both done and incomplete tasks by default."""
        todo = TodoList()
        task1 = todo.add("First")
        task2 = todo.add("Second")
        task3 = todo.add("Third")
        todo.complete(task2.id)
        tasks = todo.list()
        assert len(tasks) == 3
        assert tasks[0] is task1
        assert tasks[1] is task2
        assert tasks[2] is task3

    def test_list_include_done_true(self) -> None:
        """list(include_done=True) returns all tasks."""
        todo = TodoList()
        task1 = todo.add("Incomplete")
        task2 = todo.add("Complete")
        todo.complete(task2.id)
        tasks = todo.list(include_done=True)
        assert len(tasks) == 2
        assert task1 in tasks
        assert task2 in tasks

    def test_list_include_done_false(self) -> None:
        """list(include_done=False) returns only incomplete tasks."""
        todo = TodoList()
        task1 = todo.add("Incomplete 1")
        task2 = todo.add("Complete")
        task3 = todo.add("Incomplete 2")
        todo.complete(task2.id)
        tasks = todo.list(include_done=False)
        assert len(tasks) == 2
        assert task1 in tasks
        assert task3 in tasks
        assert task2 not in tasks

    def test_list_ordered_by_id(self) -> None:
        """Tasks are returned sorted by id."""
        todo = TodoList()
        task1 = todo.add("First")
        task2 = todo.add("Second")
        task3 = todo.add("Third")
        tasks = todo.list()
        assert tasks == [task1, task2, task3]
        ids = [t.id for t in tasks]
        assert ids == sorted(ids)


class TestTodoListPriority:
    """Test priority support on Task/TodoList.add/list."""

    def test_add_default_priority_is_zero(self) -> None:
        """Tasks default to priority 0 when not specified."""
        todo = TodoList()
        task = todo.add("Task")
        assert task.priority == 0

    def test_add_negative_priority_raises_valueerror(self) -> None:
        """Adding a task with negative priority raises ValueError."""
        todo = TodoList()
        with pytest.raises(ValueError, match="priority must not be negative"):
            todo.add("Task", priority=-1)

    def test_rejected_add_does_not_consume_an_id(self) -> None:
        """A failed add() (negative priority) leaves the id counter untouched."""
        todo = TodoList()
        with pytest.raises(ValueError):
            todo.add("Task", priority=-1)
        task = todo.add("Task")
        assert task.id == 1

    def test_list_sort_by_priority_orders_high_first(self) -> None:
        """sort_by_priority=True orders tasks from highest to lowest priority."""
        todo = TodoList()
        low = todo.add("Low", priority=1)
        high = todo.add("High", priority=5)
        mid = todo.add("Mid", priority=3)
        tasks = todo.list(sort_by_priority=True)
        assert tasks == [high, mid, low]

    def test_list_sort_by_priority_ties_break_by_insertion_order(self) -> None:
        """Equal-priority tasks keep their id order (stable sort)."""
        todo = TodoList()
        first = todo.add("First", priority=2)
        second = todo.add("Second", priority=2)
        third = todo.add("Third", priority=2)
        tasks = todo.list(sort_by_priority=True)
        assert tasks == [first, second, third]

    def test_list_sort_by_priority_combines_with_include_done_false(self) -> None:
        """Priority sort still respects the include_done filter."""
        todo = TodoList()
        low = todo.add("Low", priority=1)
        high = todo.add("High", priority=5)
        todo.complete(high.id)
        tasks = todo.list(include_done=False, sort_by_priority=True)
        assert tasks == [low]

    def test_list_sort_by_priority_empty_list(self) -> None:
        """sort_by_priority on an empty TodoList returns an empty list."""
        todo = TodoList()
        assert todo.list(sort_by_priority=True) == []

    def test_list_default_sort_by_priority_is_false(self) -> None:
        """Without sort_by_priority, list() still orders by id regardless of priority."""
        todo = TodoList()
        high = todo.add("High", priority=5)
        low = todo.add("Low", priority=1)
        tasks = todo.list()
        assert tasks == [high, low]


class TestTodoListIntegration:
    """Integration tests for TodoList."""

    def test_full_workflow(self) -> None:
        """Complete workflow: add, complete, list, remove."""
        todo = TodoList()
        task1 = todo.add("Buy milk")
        task2 = todo.add("Walk dog")
        task3 = todo.add("Code review")

        # Complete one task
        todo.complete(task2.id)

        # List all tasks
        all_tasks = todo.list()
        assert len(all_tasks) == 3

        # List only incomplete
        incomplete = todo.list(include_done=False)
        assert len(incomplete) == 2
        assert task1 in incomplete
        assert task3 in incomplete

        # Remove a task
        todo.remove(task1.id)
        remaining = todo.list()
        assert len(remaining) == 2
        assert task1 not in remaining

    def test_multiple_instances_independent(self) -> None:
        """Multiple TodoList instances don't share state."""
        todo1 = TodoList()
        todo2 = TodoList()

        task1 = todo1.add("Task 1")
        task2 = todo2.add("Task 2")

        assert task1.id == 1
        assert task2.id == 1  # separate counter

        todo1_tasks = todo1.list()
        todo2_tasks = todo2.list()

        assert len(todo1_tasks) == 1
        assert len(todo2_tasks) == 1
        assert todo1_tasks[0] is task1
        assert todo2_tasks[0] is task2

    def test_complete_idempotent_for_already_done(self) -> None:
        """Completing an already-completed task is safe."""
        todo = TodoList()
        task = todo.add("Task")
        todo.complete(task.id)
        assert task.done is True

        # Complete again — should work without error
        completed_again = todo.complete(task.id)
        assert completed_again.done is True

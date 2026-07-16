import pytest

from mock_agent.catalog import TaskCatalog, UnknownTaskError


def test_catalog_exposes_registered_sales_tasks_by_canonical_id():
    catalog = TaskCatalog.from_sales_dataset()

    summaries = catalog.list_tasks()
    task = catalog.get_task("sales.zoom_calendar_conflict")

    assert len(summaries) == 100
    assert len({summary.task_id for summary in summaries}) == 100
    assert task.summary in summaries
    assert task.summary.prompt[-1].role == "user"
    assert task.summary.tools == tuple(task.info["zapier_tools"])
    assert task.summary.assertion_count == len(task.info["assertions"])
    with pytest.raises(UnknownTaskError, match="sales.not_registered"):
        catalog.get_task("sales.not_registered")

import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime
from models import Flight, FlightPair


def _make_done_result():
    return {
        "status": "ok",
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": ["徒步"],
        "itineraries": [], "warnings": [], "errors": [],
    }


def _make_done_result_with_errors():
    return {
        "status": "error",
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": [],
        "itineraries": [], "warnings": [], "errors": ["LLM failed"],
    }


def _make_interrupt_result():
    class _InterruptVal:
        value = {"type": "confirm_params", "message": "已解析...", "parsed": {}}
    return {"__interrupt__": [_InterruptVal()]}


def test_handle_result_emits_done(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result())
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "done"


def test_handle_result_emits_hitl_request(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import _handle_result
    _handle_result("job1", _make_interrupt_result())
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "hitl_request"
    assert "interrupt_id" in data


def test_handle_result_adds_to_dataset_on_success(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mock_add = mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    result = _make_done_result()
    _handle_result("job1", result)
    mock_add.assert_called_once_with("job1", result)


def test_handle_result_skips_dataset_on_error(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mock_add = mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result_with_errors())
    mock_add.assert_not_called()


def test_auto_add_to_dataset_creates_example(mocker):
    mock_dataset = MagicMock()
    mock_dataset.id = "ds-123"
    mock_client = MagicMock()
    mock_client.read_dataset.return_value = mock_dataset
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": ["徒步"],
        "itineraries": [], "warnings": [], "errors": [],
    })
    mock_client.create_example.assert_called_once()
    call_kwargs = mock_client.create_example.call_args[1]
    assert call_kwargs["inputs"]["destination"] == "川西"
    assert call_kwargs["metadata"]["job_id"] == "job1"
    assert call_kwargs["dataset_id"] == "ds-123"


def test_auto_add_to_dataset_creates_dataset_if_missing(mocker):
    mock_new_dataset = MagicMock()
    mock_new_dataset.id = "ds-new"
    mock_client = MagicMock()
    mock_client.read_dataset.side_effect = Exception("not found")
    mock_client.create_dataset.return_value = mock_new_dataset
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {"destination": "川西"})
    mock_client.create_dataset.assert_called_once()
    mock_client.create_example.assert_called_once()


def test_auto_add_to_dataset_swallows_exception(mocker):
    mock_client = MagicMock()
    mock_client.read_dataset.side_effect = Exception("network error")
    mock_client.create_dataset.side_effect = Exception("network error")
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {"destination": "川西"})  # must not raise


def test_resume_plan_idempotent(mocker):
    mock_r = MagicMock()
    mock_r.set.return_value = None
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import resume_plan
    resume_plan("job1", "user reply", "iid-1")
    mock_r.xadd.assert_not_called()


def test_make_node_wrapper_emits_progress(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import make_node_wrapper

    called = []

    async def fake_node(state, config):
        called.append(True)
        return {}

    # Simulate the module path that node_wrapper uses
    fake_node.__module__ = "agent.nodes.discover_pois"

    wrapped = make_node_wrapper("job-test")(fake_node)

    import asyncio
    asyncio.run(wrapped({}, {}))

    assert called == [True]
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "progress"
    assert data["node"] == "discover_pois"
    assert "景点" in data["message"]


def test_run_plan_emits_error_on_exception(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)

    mocker.patch("worker.tasks.asyncio.run", side_effect=RuntimeError("test failure"))

    from worker.tasks import run_plan
    with pytest.raises(RuntimeError):
        run_plan("job-err", {})

    calls = [json.loads(c[0][1]["data"]) for c in mock_r.xadd.call_args_list]
    error_calls = [c for c in calls if c.get("type") == "error"]
    assert len(error_calls) == 1
    assert "RuntimeError" in error_calls[0]["message"]

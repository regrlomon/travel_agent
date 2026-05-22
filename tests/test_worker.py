import pytest
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from models import Flight, FlightPair


def _make_done_result():
    return {"status": "ok", "itineraries": [], "warnings": []}


def _make_interrupt_result():
    class _InterruptVal:
        value = {"type": "confirm_params", "message": "已解析...", "parsed": {}}
    return {"__interrupt__": [_InterruptVal()]}


def test_handle_result_emits_done(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result())
    mock_r.xadd.assert_called_once()
    call_args = mock_r.xadd.call_args
    data = json.loads(call_args[0][1]["data"])
    assert data["type"] == "done"


def test_handle_result_emits_hitl_request(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import _handle_result
    _handle_result("job1", _make_interrupt_result())
    mock_r.xadd.assert_called_once()
    call_args = mock_r.xadd.call_args
    data = json.loads(call_args[0][1]["data"])
    assert data["type"] == "hitl_request"
    assert "interrupt_id" in data


def test_resume_plan_idempotent(mocker):
    mock_r = MagicMock()
    mock_r.set.return_value = None   # lock already held → returns None (falsy)
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import resume_plan
    resume_plan("job1", "user reply", "iid-1")
    mock_r.xadd.assert_not_called()

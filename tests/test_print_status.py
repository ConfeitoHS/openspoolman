def _abort_tracker(monkeypatch, running_ids=()):
    import filament_usage_tracker as fut

    calls = []
    monkeypatch.setattr(fut, "get_running_layer_tracking_print_ids", lambda: list(running_ids))
    tracker = fut.FilamentUsageTracker()
    tracker._set_layer_tracking_status = lambda status, target_print_id=None, extra_fields=None: calls.append((status, target_print_id))
    return fut, tracker, calls


def test_cancel_during_prepare_is_cancelled(monkeypatch):
    fut, tracker, calls = _abort_tracker(monkeypatch)
    aborted = []
    tracker.active_model = {}
    tracker._handle_print_abort = lambda status: aborted.append(status)

    tracker.on_message({"print": {"command": "push_status", "gcode_state": "PREPARE"}})
    tracker.on_message({"print": {"command": "push_status", "gcode_state": "FAILED", "print_error": fut.PRINT_ERROR_CANCELLED}})

    assert aborted == [fut.LAYER_TRACKING_STATUS_ABORTED]


def test_real_failure_stays_failed(monkeypatch):
    fut, tracker, calls = _abort_tracker(monkeypatch)
    aborted = []
    tracker.active_model = {}
    tracker._handle_print_abort = lambda status: aborted.append(status)

    tracker.on_message({"print": {"command": "push_status", "gcode_state": "RUNNING"}})
    tracker.on_message({"print": {"command": "push_status", "gcode_state": "FAILED", "print_error": 12345}})

    assert aborted == [fut.LAYER_TRACKING_STATUS_FAILED]


def test_untracked_running_print_is_closed(monkeypatch):
    fut, tracker, calls = _abort_tracker(monkeypatch, running_ids=[85])

    tracker.on_message({"print": {"command": "push_status", "gcode_state": "RUNNING"}})
    assert calls == []
    tracker.on_message({"print": {"command": "push_status", "gcode_state": "FAILED", "print_error": fut.PRINT_ERROR_CANCELLED}})

    assert calls == [(fut.LAYER_TRACKING_STATUS_ABORTED, 85)]

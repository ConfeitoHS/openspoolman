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


def test_old_rows_next_to_finished_print_are_cancelled(monkeypatch):
    fut, tracker, calls = _abort_tracker(monkeypatch, running_ids=[80])
    tracker.active_model = {}
    tracker.gcode_state = "RUNNING"

    def _end():
        tracker.active_model = None
    tracker._handle_print_end = _end

    tracker.on_message({"print": {"command": "push_status", "gcode_state": "FINISH"}})

    assert calls == [(fut.LAYER_TRACKING_STATUS_ABORTED, 80)]


def _resume_tracker(monkeypatch, tmp_path, running_ids=()):
    import filament_usage_tracker as fut

    monkeypatch.setattr(fut, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(fut, "get_running_layer_tracking_print_ids", lambda: list(running_ids))
    monkeypatch.setattr(fut, "get_all_filament_usage_for_print", lambda print_id: {})
    model = tmp_path / "model.3mf"
    model.write_bytes(b"3mf")
    tracker = fut.FilamentUsageTracker()
    monkeypatch.setattr(tracker, "_load_model", lambda path, gcode: setattr(tracker, "active_model", {0: {}, 1: {}}))
    return fut, tracker, model


def test_resume_after_restart_restores_print_id(monkeypatch, tmp_path):
    fut, tracker, model = _resume_tracker(monkeypatch, tmp_path)
    fut.save_checkpoint(model_path=str(model), current_layer=2, task_id="t", subtask_id="s",
                        ams_mapping=[0], gcode_file_name="plate_1.gcode", print_id=137)

    tracker._attempt_print_resume("t", "s")

    assert tracker.print_id == 137
    assert tracker.current_layer == 2


def test_resume_from_old_checkpoint_uses_running_print(monkeypatch, tmp_path):
    fut, tracker, model = _resume_tracker(monkeypatch, tmp_path, running_ids=[120, 137])
    fut.save_checkpoint(model_path=str(model), current_layer=2, task_id="t", subtask_id="s",
                        ams_mapping=[0], gcode_file_name="plate_1.gcode")

    tracker._attempt_print_resume("t", "s")

    assert tracker.print_id == 137


def test_resume_backfills_history_and_catches_up(monkeypatch, tmp_path):
    fut, tracker, model = _resume_tracker(monkeypatch, tmp_path)
    usage = {0: {0: 100.0}, 1: {0: 50.0, 1: 20.0}, 2: {0: 10.0}, 3: {1: 30.0}}
    monkeypatch.setattr(tracker, "_load_model", lambda path, gcode: setattr(tracker, "active_model", usage))
    monkeypatch.setattr(fut, "TRACK_LAYER_USAGE", True)
    consumed, history = [], {}
    monkeypatch.setattr(fut, "consumeSpool", lambda spool_id, use_length=None: consumed.append((spool_id, round(use_length, 1))))
    monkeypatch.setattr(fut, "update_filament_spool", lambda *a: None)
    monkeypatch.setattr(fut, "update_filament_grams_used", lambda pid, key, g, length_used=None: history.__setitem__(key, length_used))
    monkeypatch.setattr(fut, "update_layer_tracking", lambda *a, **k: None)
    monkeypatch.setattr(fut, "update_checkpoint_layer", lambda layer: None)
    monkeypatch.setattr(tracker, "_get_spool_id_for_filament", lambda f: 10 + f)
    monkeypatch.setattr(tracker, "_tray_uid_for_filament", lambda f: f"uid{f}")
    monkeypatch.setattr(tracker, "_lookup_spool_for_tray", lambda uid: 10 + int(uid[3:]))
    monkeypatch.setattr(tracker, "_get_spool_data", lambda spool_id: {"filament": {"diameter": 1.75, "density": 1.24}})

    # restart: checkpoint at layer 1 (already consumed in Spoolman, not in history), printer at layer 3
    fut.save_checkpoint(model_path=str(model), current_layer=1, task_id="t", subtask_id="s",
                        ams_mapping=[0, 1], gcode_file_name="plate.gcode", print_id=137)
    tracker.current_layer = 3
    tracker._attempt_print_resume("t", "s")

    # layers 0..1 only recorded in history, layers 2..3 consumed in Spoolman and history
    assert sorted(consumed) == [(10, 10.0), (11, 30.0)]
    assert history[1] == 160.0 and history[2] == 50.0
    assert tracker.current_layer == 3

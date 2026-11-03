from external_trays import (
    external_ams_id_from_mapping,
    find_external_tray,
    get_external_trays,
    is_external_tray,
)


def _vir_slot_config():
    return {
        "vir_slot": [
            {"id": "254", "tray_type": "TPU"},
            {"id": "255", "tray_type": ""},
        ]
    }


def test_single_external_from_vt_tray():
    trays = get_external_trays({"vt_tray": {"id": "254", "tray_type": "PLA"}})
    assert [(t["ams_id"], t["tray_id"]) for t in trays] == [(255, 254)]
    assert trays[0]["data"]["tray_type"] == "PLA"


def test_missing_external_still_renders_empty_slot():
    config = {}
    trays = get_external_trays(config)
    assert [(t["ams_id"], t["tray_id"]) for t in trays] == [(255, 254)]
    assert trays[0]["data"] is config["vt_tray"]


def test_dual_external_from_vir_slot():
    trays = get_external_trays(_vir_slot_config())
    assert [(t["ams_id"], t["tray_id"], t["label"]) for t in trays] == [
        (254, 254, "External Spool (Left)"),
        (255, 254, "External Spool (Right)"),
    ]
    assert find_external_tray(_vir_slot_config(), "254")["data"]["tray_type"] == "TPU"


def test_is_external_tray():
    assert is_external_tray("255", "254")
    assert is_external_tray(254, 254)
    assert not is_external_tray(0, 1)
    assert not is_external_tray(128, 0)
    assert not is_external_tray(None, None)


def test_mapping_to_external_ams_id():
    assert external_ams_id_from_mapping(254, dual=False) == 255
    assert external_ams_id_from_mapping(255, dual=False) is None
    assert external_ams_id_from_mapping(254, dual=True) == 254
    assert external_ams_id_from_mapping(255, dual=True) == 255
    assert external_ams_id_from_mapping(3, dual=True) is None


def test_reset_external_slot_is_empty():
    from spoolman_service import augmentTrayDataWithSpoolMan, trayUid
    import json

    spool = {
        "id": 41,
        "extra": {"active_tray": json.dumps(trayUid(255, 254))},
        "filament": {"name": "ASA White", "vendor": {"name": "Sunlu"}, "material": "ASA"},
        "remaining_weight": 1000.0,
    }
    tray = {"id": "255", "tray_type": "", "tray_color": "00000000"}
    augmentTrayDataWithSpoolMan([spool], tray, 255, 254)
    assert tray["spool_id"] is None
    assert not tray.get("spool_material")


def test_job_mapping_decoding():
    from external_trays import tray_from_job_mapping

    # Values observed on an X2D: AMS 0 slot 4, AMS HT (128), left external, unused.
    assert tray_from_job_mapping(3) == (0, 3)
    assert tray_from_job_mapping(0x8000) == (128, 0)
    assert tray_from_job_mapping(0xFE00) == (254, 254)
    assert tray_from_job_mapping(0xFF00) == (255, 254)
    assert tray_from_job_mapping(0x0102) == (1, 2)
    assert tray_from_job_mapping(65535) is None


def test_flat_mapping_decoding():
    from external_trays import tray_from_flat_mapping

    assert tray_from_flat_mapping(3, dual=True) == (0, 3)
    assert tray_from_flat_mapping(6, dual=True) == (1, 2)
    assert tray_from_flat_mapping(128, dual=True) == (128, 0)
    assert tray_from_flat_mapping(254, dual=False) == (255, 254)
    assert tray_from_flat_mapping(-1, dual=True) is None


def test_tracker_prefers_printer_job_mapping():
    from filament_usage_tracker import FilamentUsageTracker
    from spoolman_service import trayUid

    tracker = FilamentUsageTracker()
    tracker.using_ams = True
    tracker.ams_mapping = [-1, -1, 3, 512]  # flat mapping that misses the AMS HT
    tracker.active_model = object()
    tracker._bind_initial_spools = lambda: None
    tracker._update_job_mapping([65535, 65535, 3, 32768])

    assert tracker._tray_uid_for_filament(2) == trayUid(0, 3)
    assert tracker._tray_uid_for_filament(3) == trayUid(128, 0)

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


def test_tool_changer_virtual_slots():
    from external_trays import get_external_trays, is_external_tray, tray_from_job_mapping

    config = {"vir_slot": [{"id": str(i), "tray_type": ""} for i in range(247, 256)]}
    trays = get_external_trays(config)
    assert [t["ams_id"] for t in trays] == list(range(255, 246, -1))
    assert trays[0]["label"] == "External Spool 1"
    assert trays[-1]["label"] == "External Spool 9"
    assert is_external_tray(247, 254)
    assert not is_external_tray(32, 0)
    assert tray_from_job_mapping(0x2000) == (32, 0)
    assert tray_from_job_mapping(0xF700) == (247, 254)


def test_zone_humidity_is_lifted_to_unit():
    from mqtt_bambulab import normalize_ams_unit

    ams = {"id": "32", "zone_info": [
        {"zone_id": 0, "humidity": "4", "humidity_raw": "23", "temp": "30.5"},
        {"zone_id": 1, "humidity": "2", "humidity_raw": "31", "temp": "31.2"},
    ]}
    normalize_ams_unit(ams)
    assert (ams["humidity"], ams["humidity_raw"], ams["temp"]) == ("2", "31", "31.2")


def test_tool_changer_merges_external_into_ams_slot():
    from external_trays import build_ams_views, get_external_trays

    vir = [{"id": str(i), "tray_type": ""} for i in range(247, 256)]
    vir[1]["tray_type"] = "TPU"  # id 248 -> slot 8
    ams = {"id": "32", "tray": [{"id": str(i)} for i in range(9)]}
    views, externals = build_ams_views([ams], get_external_trays({"vir_slot": vir}))

    assert externals == []
    slots = views[0]["slots"]
    assert [s["label"] for s in slots] == [None] * 7 + ["8-EXT", None]
    assert (slots[7]["ams_id"], slots[7]["tray_id"]) == (248, 254)
    assert (slots[0]["ams_id"], slots[0]["tray_id"]) == ("32", "0")


def test_dual_nozzle_keeps_separate_external_cards():
    from external_trays import build_ams_views, get_external_trays

    vir = [{"id": "254", "tray_type": "PLA"}, {"id": "255", "tray_type": ""}]
    ams = {"id": "0", "tray": [{"id": str(i)} for i in range(4)]}
    views, externals = build_ams_views([ams], get_external_trays({"vir_slot": vir}))

    assert len(externals) == 2
    assert all(s["label"] is None for s in views[0]["slots"])

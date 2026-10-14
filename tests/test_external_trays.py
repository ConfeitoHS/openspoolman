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

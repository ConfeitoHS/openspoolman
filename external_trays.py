"""Helpers for external (virtual) spool slots.

Single-nozzle printers report one external spool as ``vt_tray``.
Dual-nozzle printers (H2D, X2D, ...) report two external spools as a ``vir_slot`` list:
  - id "255": main extruder (right nozzle)
  - id "254": deputy extruder (left nozzle)

Every external slot is identified as (ams_id=<255|254>, tray_id=254). This matches what
Bambu Studio sends in ams_filament_setting and keeps the legacy single external spool
(255, 254) unchanged.
"""
from config import EXTERNAL_SPOOL_AMS_ID, EXTERNAL_SPOOL_ID

EXTERNAL_SPOOL_LEFT_AMS_ID = 254

# Set once the printer reports vir_slot, i.e. it has two external spools.
DUAL_EXTERNAL = False


def set_dual_external(value: bool) -> None:
  global DUAL_EXTERNAL
  DUAL_EXTERNAL = bool(value)

_LABELS = {
  EXTERNAL_SPOOL_AMS_ID: "External Spool (Right)",
  EXTERNAL_SPOOL_LEFT_AMS_ID: "External Spool (Left)",
}


def is_external_tray(ams_id, tray_id) -> bool:
  try:
    return int(tray_id) == EXTERNAL_SPOOL_ID and int(ams_id) in _LABELS
  except (TypeError, ValueError):
    return False


def has_dual_external(config: dict) -> bool:
  return bool(config.get("vir_slot"))


def get_external_trays(config: dict) -> list[dict]:
  """Return [{ams_id, tray_id, label, data}] for every external slot, left before right."""
  vir_slot = config.get("vir_slot")
  if vir_slot:
    trays = []
    for slot in vir_slot:
      try:
        ams_id = int(slot.get("id"))
      except (TypeError, ValueError):
        continue
      if ams_id not in _LABELS:
        continue
      trays.append({
        "ams_id": ams_id,
        "tray_id": EXTERNAL_SPOOL_ID,
        "label": _LABELS[ams_id],
        "data": slot,
      })
    return sorted(trays, key=lambda tray: tray["ams_id"])

  vt_tray = config.get("vt_tray")
  if vt_tray is None:
    vt_tray = {}
    config["vt_tray"] = vt_tray
  return [{
    "ams_id": EXTERNAL_SPOOL_AMS_ID,
    "tray_id": EXTERNAL_SPOOL_ID,
    "label": "External Spool",
    "data": vt_tray,
  }]


def find_external_tray(config: dict, ams_id) -> dict | None:
  for tray in get_external_trays(config):
    if str(tray["ams_id"]) == str(ams_id):
      return tray
  return None


def external_ams_id_from_mapping(mapping_value, dual: bool | None = None) -> int | None:
  """Translate a flat ams_mapping value to an external slot ams_id, if it is one.

  Dual-nozzle printers use the virtual tray id directly (255 right, 254 left);
  single-nozzle printers use 254 for their only external spool.
  """
  if dual is None:
    dual = DUAL_EXTERNAL
  try:
    value = int(mapping_value)
  except (TypeError, ValueError):
    return None
  if value == EXTERNAL_SPOOL_ID:
    return EXTERNAL_SPOOL_LEFT_AMS_ID if dual else EXTERNAL_SPOOL_AMS_ID
  if dual and value == EXTERNAL_SPOOL_AMS_ID:
    return EXTERNAL_SPOOL_AMS_ID
  return None

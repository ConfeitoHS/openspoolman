"""Helpers for external (virtual) spool slots.

Single-nozzle printers report one external spool as ``vt_tray``.
Multi-nozzle printers report their external spools as a ``vir_slot`` list, one per
nozzle, counting down from 255 (nozzle index = 255 - id):
  - H2D / X2D: "255" main extruder (right nozzle), "254" deputy extruder (left nozzle)
  - H3C: "255" ... "247", one per nozzle of the tool changer

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
# Virtual (external) slot ids count down from 255; real AMS ids stay far below this.
MIN_VIRTUAL_AMS_ID = 240


def is_virtual_ams_id(ams_id) -> bool:
  try:
    return MIN_VIRTUAL_AMS_ID <= int(ams_id) <= EXTERNAL_SPOOL_AMS_ID
  except (TypeError, ValueError):
    return False


def _external_label(ams_id: int, slot_count: int) -> str:
  if slot_count <= 2:
    return _LABELS.get(ams_id, "External Spool")
  return f"External Spool {EXTERNAL_SPOOL_AMS_ID - ams_id + 1}"


def is_external_tray(ams_id, tray_id) -> bool:
  try:
    return int(tray_id) == EXTERNAL_SPOOL_ID and is_virtual_ams_id(ams_id)
  except (TypeError, ValueError):
    return False


def has_dual_external(config: dict) -> bool:
  return bool(config.get("vir_slot"))


def get_external_trays(config: dict) -> list[dict]:
  """Return [{ams_id, tray_id, label, data}] for every external slot, left before right."""
  vir_slot = config.get("vir_slot")
  if vir_slot:
    slots = []
    for slot in vir_slot:
      try:
        ams_id = int(slot.get("id"))
      except (TypeError, ValueError):
        continue
      if is_virtual_ams_id(ams_id):
        slots.append((ams_id, slot))
    trays = [{
      "ams_id": ams_id,
      "tray_id": EXTERNAL_SPOOL_ID,
      "label": _external_label(ams_id, len(slots)),
      "data": slot,
    } for ams_id, slot in slots]
    if len(trays) <= 2:
      return sorted(trays, key=lambda tray: tray["ams_id"])  # left before right
    return sorted(trays, key=lambda tray: -tray["ams_id"])  # nozzle 1, 2, ...

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


JOB_MAPPING_UNMAPPED = 0xFFFF


def tray_from_job_mapping(value) -> tuple[int, int] | None:
  """Decode a value of the printer's push_status ``mapping`` list (one per job filament).

  Encoding is ``ams_id << 8 | slot_id``; 0xFFFF means the filament is not used.
  External slots use ams_id 254/255.
  """
  try:
    value = int(value)
  except (TypeError, ValueError):
    return None
  if value < 0 or value >= JOB_MAPPING_UNMAPPED:
    return None
  ams_id, slot_id = value >> 8, value & 0xFF
  if is_virtual_ams_id(ams_id):
    return ams_id, EXTERNAL_SPOOL_ID
  return ams_id, slot_id


def tray_from_flat_mapping(value, dual: bool | None = None) -> tuple[int, int] | None:
  """Decode a flat ``ams_mapping`` value (as sent with project_file)."""
  external_ams_id = external_ams_id_from_mapping(value, dual)
  if external_ams_id is not None:
    return external_ams_id, EXTERNAL_SPOOL_ID
  try:
    value = int(value)
  except (TypeError, ValueError):
    return None
  if value < 0:
    return None
  if 128 <= value < EXTERNAL_SPOOL_ID:
    # Single-slot AMS units (AMS HT) use their ams_id directly.
    return value, 0
  return value // 4, value % 4

# Observed H3C AMS tray "state" values: 0 empty, 21 inserted + reading RFID, 27 filament
# present, 256 empty but last RFID tag remembered, 283 filament + Bambu RFID. 160 appeared on
# trays only while a print was running (ams_status 0x300); its meaning is unknown.
TRAY_STATE_READING_RFID = 21


def _tool_snow_by_slot(nozzles) -> dict[int, int]:
  snow = {}
  for nozzle in nozzles or []:
    try:
      snow[int(nozzle["addr_id"])] = int(nozzle["snow"])
    except (KeyError, TypeError, ValueError):
      continue
  return snow


def _tray_state(tray: dict) -> int:
  try:
    return int(tray.get("state") or 0)
  except (TypeError, ValueError):
    return 0


def build_ams_views(ams_data: list[dict], external_trays: list[dict], nozzles=None) -> tuple[list[dict], list[dict]]:
  """Prepare AMS units for rendering; returns (ams_views, external_trays_to_show).

  Each view is the AMS dict plus ``slots``:
  [{data, ams_id, tray_id, label, slot_index, ext, loaded, reading}].

  On a tool changer (H3C) every slot N has AMS tray N-1, its own external slot 256-N and its
  own tool (nozzle addr N-1). One card is shown per slot: the AMS tray, with the external
  slot as a strip inside the card (``ext``) whenever it has a material configured or is
  loaded. ``loaded`` tells which source the slot's tool currently holds ("ams"/"ext"), taken
  from the tool's ``snow`` (ams_id << 8 | slot). ``reading`` is set while the AMS reads a
  freshly inserted spool's RFID (tray state 21).
  """
  ext_by_slot = {}
  target = None
  if len(external_trays) > 2:
    candidates = [ams for ams in ams_data if len(ams.get("tray") or []) == len(external_trays)]
    if len(candidates) == 1:
      target = candidates[0]
      ext_by_slot = {EXTERNAL_SPOOL_AMS_ID - external["ams_id"]: external for external in external_trays}
  tool_snow = _tool_snow_by_slot(nozzles) if target is not None else {}

  views = []
  for ams in ams_data:
    try:
      ams_numeric_id = int(ams.get("id"))
    except (TypeError, ValueError):
      ams_numeric_id = None
    slots = []
    for tray in ams.get("tray") or []:
      try:
        slot_index = int(tray.get("id"))
      except (TypeError, ValueError):
        slot_index = len(slots)

      external = ext_by_slot.get(slot_index) if ams is target else None
      snow = tool_snow.get(slot_index)
      loaded = None
      if snow is not None and ams_numeric_id is not None and snow == (ams_numeric_id << 8 | slot_index):
        loaded = "ams"
      elif snow is not None and external and snow >> 8 == external["ams_id"] and snow & 0xFF != 0xFF:
        loaded = "ext"

      ext_slot = None
      if external and ((external["data"].get("tray_type") or "").strip() or loaded == "ext"):
        ext_slot = {
          "data": external["data"],
          "ams_id": external["ams_id"],
          "tray_id": external["tray_id"],
          "label": f"{slot_index + 1}-EXT",
          "loaded": loaded == "ext",
        }

      slots.append({
        "data": tray,
        "ams_id": ams.get("id"),
        "tray_id": tray.get("id"),
        "label": None,
        "slot_index": slot_index,
        "ext": ext_slot,
        "loaded": loaded == "ams",
        "reading": _tray_state(tray) == TRAY_STATE_READING_RFID,
      })
    views.append(dict(ams, slots=slots))

  return views, ([] if target is not None else external_trays)

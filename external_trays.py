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

# AMS tray "state" of a tool-changer slot that is set to "external spool only" on the printer
# (observed on the H3C; it stays set whether or not a material is configured for the slot).
TRAY_STATE_EXTERNAL_ONLY = 160


def _is_external_only(tray: dict) -> bool:
  try:
    return int(tray.get("state")) == TRAY_STATE_EXTERNAL_ONLY
  except (TypeError, ValueError):
    return False


def _ams_tray_has_filament(tray: dict) -> bool:
  # Empty trays only report id/state/print_status; occupied ones carry the filament fields.
  return "tray_type" in tray


def build_ams_views(ams_data: list[dict], external_trays: list[dict]) -> tuple[list[dict], list[dict]]:
  """Prepare AMS units for rendering; returns (ams_views, external_trays_to_show).

  Each view is the AMS dict plus ``slots``: [{data, ams_id, tray_id, label, slot_index, ext}].

  On a tool changer (H3C) every nozzle slot N has AMS tray N-1 and its own external slot
  256-N, so both are shown in that slot's position:
  - slot set to external-only on the printer, or no AMS filament: only the external slot,
    labelled "N-EXT"
  - AMS filament and an external material configured: the AMS tray, with the external slot
    ("N-EXT") stacked below it in ``ext``
  - otherwise: only the AMS tray
  """
  ext_by_slot = {}
  target = None
  if len(external_trays) > 2:
    candidates = [ams for ams in ams_data if len(ams.get("tray") or []) == len(external_trays)]
    if len(candidates) == 1:
      target = candidates[0]
      ext_by_slot = {EXTERNAL_SPOOL_AMS_ID - external["ams_id"]: external for external in external_trays}

  views = []
  for ams in ams_data:
    slots = []
    for tray in ams.get("tray") or []:
      try:
        slot_index = int(tray.get("id"))
      except (TypeError, ValueError):
        slot_index = len(slots)
      external = ext_by_slot.get(slot_index) if ams is target else None
      ext_slot = None
      if external:
        ext_slot = {
          "data": external["data"],
          "ams_id": external["ams_id"],
          "tray_id": external["tray_id"],
          "label": f"{slot_index + 1}-EXT",
          "slot_index": slot_index,
          "ext": None,
        }
      ext_configured = bool(external and (external["data"].get("tray_type") or "").strip())

      if ext_slot and (_is_external_only(tray) or (ext_configured and not _ams_tray_has_filament(tray))):
        slots.append(ext_slot)
      else:
        slots.append({
          "data": tray,
          "ams_id": ams.get("id"),
          "tray_id": tray.get("id"),
          "label": None,
          "slot_index": slot_index,
          "ext": ext_slot if ext_configured else None,
        })
    views.append(dict(ams, slots=slots))

  return views, ([] if target is not None else external_trays)

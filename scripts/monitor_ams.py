"""Record AMS tray state changes over LAN MQTT for a few seconds.

Usage:
  python scripts/monitor_ams.py --ip 192.168.x.x --serial <SERIAL> --code <ACCESS_CODE> [--seconds 10]

Prints a line whenever a tray's state/print_status/material or an AMS bit field changes,
and saves every received report to data/ams_monitor.json.
"""
import argparse
import json
import os
import ssl
import time
from pathlib import Path

import paho.mqtt.client as mqtt

try:
  from dotenv import load_dotenv
  load_dotenv(Path(__file__).resolve().parent.parent / "config.env")
except ImportError:
  pass

BIT_FIELDS = ("tray_exist_bits", "tray_reading_bits", "tray_read_done_bits", "tray_now", "tray_tar")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--ip", default=os.getenv("PRINTER_IP"))
  parser.add_argument("--serial", default=os.getenv("PRINTER_ID"))
  parser.add_argument("--code", default=os.getenv("PRINTER_ACCESS_CODE"))
  parser.add_argument("--seconds", type=float, default=10)
  parser.add_argument("--pushall-every", type=float, default=2)
  parser.add_argument("--out", default="data/ams_monitor.json")
  args = parser.parse_args()

  start = time.time()
  last = {}
  received = []

  def stamp():
    return f"{time.time() - start:6.2f}s"

  def note(key, value):
    if last.get(key) != value:
      print(f"{stamp()}  {key}: {last.get(key, '-')} -> {value}", flush=True)
      last[key] = value

  def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe(f"device/{args.serial}/report")
    client.publish(f"device/{args.serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

  def on_message(client, userdata, msg):
    try:
      data = json.loads(msg.payload)
    except ValueError:
      return
    received.append({"t": round(time.time() - start, 2), "data": data})
    print_obj = data.get("print", {})
    if "ams_status" in print_obj:
      status = int(print_obj["ams_status"] or 0)
      note("ams_status", f"{status} (main {status >> 8}, sub {status & 0xFF})")
    if print_obj.get("command") not in (None, "push_status"):
      print(f"{stamp()}  command: {json.dumps({k: v for k, v in print_obj.items() if k != 'ams'})[:200]}", flush=True)
    ams = print_obj.get("ams") or {}
    for field in BIT_FIELDS:
      if field in ams:
        note(field, ams[field])
    for unit in ams.get("ams") or []:
      for tray in unit.get("tray") or []:
        slot = f"slot {int(tray.get('id', 0)) + 1}"
        if "state" in tray:
          state = int(tray["state"] or 0)
          note(f"{slot} state", f"{state} ({state:09b})")
        if "print_status" in tray:
          note(f"{slot} print_status", tray["print_status"])
        if "tray_type" in tray or "tray_uuid" in tray:
          note(f"{slot} filament", f"{tray.get('tray_type')} {tray.get('tray_color')} uuid={str(tray.get('tray_uuid', ''))[:8]}")

  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
  client.username_pw_set("bblp", args.code)
  client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
  client.tls_insecure_set(True)
  client.on_connect = on_connect
  client.on_message = on_message
  client.connect(args.ip, 8883, 60)
  client.loop_start()

  next_push = start + args.pushall_every
  while time.time() - start < args.seconds:
    if time.time() >= next_push:
      client.publish(f"device/{args.serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
      next_push += args.pushall_every
    time.sleep(0.1)
  client.loop_stop()
  client.disconnect()

  text = json.dumps(received, indent=1, ensure_ascii=False).replace(args.serial, f"{args.serial[:3]}***{args.serial[-2:]}")
  Path(args.out).parent.mkdir(parents=True, exist_ok=True)
  Path(args.out).write_text(text, encoding="utf-8")
  print(f"{stamp()}  done, {len(received)} reports saved to {args.out}")


if __name__ == "__main__":
  main()

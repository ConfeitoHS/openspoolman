"""Dump a full printer status report (pushall) over LAN MQTT to a JSON file.

Usage:
  python scripts/dump_mqtt.py --ip 192.168.x.x --serial <SERIAL> --code <ACCESS_CODE> [--out data/mqtt_dump.json]

Values can also come from PRINTER_IP / PRINTER_ID / PRINTER_ACCESS_CODE (env or config.env).
The serial number is masked in the output so the file is safe to share.
"""
import argparse
import json
import os
import ssl
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

try:
  from dotenv import load_dotenv
  load_dotenv(Path(__file__).resolve().parent.parent / "config.env")
except ImportError:
  pass


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--ip", default=os.getenv("PRINTER_IP"))
  parser.add_argument("--serial", default=os.getenv("PRINTER_ID"))
  parser.add_argument("--code", default=os.getenv("PRINTER_ACCESS_CODE"))
  parser.add_argument("--out", default="data/mqtt_dump.json")
  parser.add_argument("--timeout", type=int, default=20)
  args = parser.parse_args()

  if not (args.ip and args.serial and args.code):
    sys.exit("PRINTER_IP, PRINTER_ID and PRINTER_ACCESS_CODE are required (args or config.env)")

  messages = []

  def on_connect(client, userdata, flags, reason_code, properties):
    print(f"connected: {reason_code}")
    client.subscribe(f"device/{args.serial}/report")
    client.publish(
      f"device/{args.serial}/request",
      json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
    )

  def on_message(client, userdata, msg):
    try:
      messages.append(json.loads(msg.payload))
    except ValueError:
      return

  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
  client.username_pw_set("bblp", args.code)
  client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
  client.tls_insecure_set(True)
  client.on_connect = on_connect
  client.on_message = on_message
  client.connect(args.ip, 8883, 60)
  client.loop_start()

  deadline = time.time() + args.timeout
  while time.time() < deadline:
    if any("ams" in m.get("print", {}) for m in messages):
      time.sleep(2)  # collect a few follow-up messages
      break
    time.sleep(0.5)
  client.loop_stop()
  client.disconnect()

  masked = f"{args.serial[:3]}***{args.serial[-2:]}"
  text = json.dumps(messages, indent=2, ensure_ascii=False).replace(args.serial, masked)
  Path(args.out).parent.mkdir(parents=True, exist_ok=True)
  Path(args.out).write_text(text, encoding="utf-8")
  print(f"saved {len(messages)} messages to {args.out}")


if __name__ == "__main__":
  main()

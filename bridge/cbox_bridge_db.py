"""
CBOX <-> RHEL MQTT bridge with PostgreSQL logging.

- RHEL -> CBOX : publishes test_var to   data/1234/factory/task1//1
- CBOX -> RHEL : receives set_var from   cmd/1234/factory/task1//1
- Every message (both directions) is stored in table cbox_tag_log.

All settings come from environment variables (or a .env file).
"""
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import Json


# ---------------------------------------------------------------- config
def load_env_file():
    """Load KEY=VALUE pairs from a .env file (env vars already set win)."""
    candidates = [
        os.getenv("CBOX_ENV_FILE"),
        Path(__file__).resolve().parent.parent / ".env",
        Path.home() / "cbox" / "cbox.env",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            for line in Path(c).read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return str(c)
    return None


ENV_FILE = load_env_file()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
TOPIC_DATA = os.getenv("TOPIC_DATA", "data/1234/factory/task1//1")  # RHEL -> CBOX
TOPIC_CMD = os.getenv("TOPIC_CMD", "cmd/1234/factory/task1//1")     # CBOX -> RHEL
GROUP_NAME = os.getenv("GROUP_NAME", "data1")
TAG_NAME = os.getenv("TAG_NAME", "test_var")
TAG_KEY = os.getenv("TAG_KEY", "V0")

SEND_COUNTER = os.getenv("SEND_COUNTER", "true").lower() == "true"
SEND_INTERVAL = float(os.getenv("SEND_INTERVAL", "5"))

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "cbox_db"),
    user=os.getenv("DB_USER", "cbox"),
    password=os.getenv("DB_PASSWORD", ""),
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("cbox-bridge")


# ---------------------------------------------------------------- database
db = None


def db_connect():
    global db
    while True:
        try:
            db = psycopg2.connect(**DB)
            db.autocommit = True
            log.info("Connected to PostgreSQL %s:%s/%s", DB["host"], DB["port"], DB["dbname"])
            return
        except psycopg2.OperationalError as e:
            log.warning("PostgreSQL not ready (%s), retrying in 5s", str(e).strip())
            time.sleep(5)


def save(tag, value, direction, raw):
    for attempt in (1, 2):
        try:
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO cbox_tag_log (tag_name, value, direction, raw) "
                    "VALUES (%s, %s, %s, %s)",
                    (tag, value, direction, Json(raw)),
                )
            return
        except (psycopg2.InterfaceError, psycopg2.OperationalError):
            log.warning("DB connection lost, reconnecting")
            db_connect()


# ---------------------------------------------------------------- mqtt
value = 0


def send_to_cbox(client, v):
    msg = {
        TAG_KEY: str(v),
        "_groupName": GROUP_NAME,
        "_terminalTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    client.publish(TOPIC_DATA, json.dumps(msg))
    save(TAG_NAME, v, "RHEL->CBOX", msg)
    log.info("RHEL -> CBOX : %s = %s", TAG_NAME, v)


def on_connect(client, userdata, flags, rc, properties=None):
    log.info("Connected to MQTT broker %s:%s (rc=%s)", MQTT_HOST, MQTT_PORT, rc)
    client.subscribe(TOPIC_CMD)


def on_message(client, userdata, msg):
    global value
    try:
        data = json.loads(msg.payload.decode())
        if data.get("type") == "set_var" and TAG_KEY in data.get("payload", {}):
            new_v = int(float(data["payload"][TAG_KEY]))
            save(TAG_NAME, new_v, "CBOX->RHEL", data)
            log.info("CBOX -> RHEL : user set %s = %s", TAG_NAME, new_v)
            value = new_v
            send_to_cbox(client, value)  # confirm back to CBOX
    except Exception as e:  # noqa: BLE001
        log.error("Bad message on %s: %s (%s)", msg.topic, msg.payload[:200], e)


def main():
    global value
    log.info("Config file: %s", ENV_FILE or "none (using environment)")
    db_connect()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rhel-cbox-bridge")
    except AttributeError:  # paho-mqtt < 2.0
        client = mqtt.Client(client_id="rhel-cbox-bridge")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            break
        except OSError as e:
            log.warning("MQTT broker not reachable (%s), retrying in 5s", e)
            time.sleep(5)
    client.loop_start()

    try:
        while True:
            if SEND_COUNTER:
                value += 1
                send_to_cbox(client, value)
            time.sleep(SEND_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        if db:
            db.close()
        log.info("Stopped")


if __name__ == "__main__":
    main()

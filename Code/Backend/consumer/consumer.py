"""consumer.py — Async MQTT -> TimescaleDB ingestion pipeline.

Subscribes to a wildcard MQTT topic, parses machine_id and sensor_type from
the topic path, and writes one row per window into the appropriate
hypertable (telemetry_current or telemetry_vibration) with raw samples
stored as DOUBLE PRECISION[] columns.

Topic schema (matches sensor_simulator.py output):
    smartwatch/<factory>/<line>/<machine>/<sensor_type>
    e.g. smartwatch/factory1/line1/motorA/current

Run from the Backend/ folder (so .env is found):
    python -m consumer.consumer
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

import aiomqtt
import asyncpg
from dotenv import load_dotenv

load_dotenv()  # picks up DB_DSN from Backend/.env

MQTT_HOST = "localhost"
MQTT_PORT = 1883
TOPIC_FILTER = (
    "smartwatch/+/+/+/+"  # smartwatch/<factory>/<line>/<machine>/<sensor_type>
)

DB_DSN = os.environ.get("DB_DSN", "postgresql://postgres:postgres@localhost:5433/iiot")

# Map sensor_type (from topic) -> (table_name, expected channel keys)
TABLE_MAP = {
    "current": ("telemetry_current", ["Ia", "Ib", "Ic"]),
    "vibration": (
        "telemetry_vibration",
        ["Vib_axial", "Vib_base", "Vib_carc", "Vib_acpe", "Vib_acpi"],
    ),
}

RECONNECT_DELAY_SECONDS = 5
DB_POOL_MIN_SIZE = 2
DB_POOL_MAX_SIZE = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("consumer")


async def create_pool():
    pool = await asyncpg.create_pool(
        dsn=DB_DSN,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
    )
    logger.info(
        "Connected to TimescaleDB (pool size %d-%d)", DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE
    )
    return pool


async def insert_window(pool, table, channel_cols, row):
    columns = ["machine_id", "time", "sample_rate_hz"] + channel_cols
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    col_list = ", ".join(f'"{c}"' for c in columns)

    values = [row["machine_id"], row["ts"], row["sample_rate_hz"]]
    values.extend(row["channels"][c] for c in channel_cols)

    query = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    async with pool.acquire() as conn:
        await conn.execute(query, *values)


def parse_topic(topic):
    """smartwatch/<factory>/<line>/<machine>/<sensor_type> -> (machine_id, sensor_type)"""
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "smartwatch":
        return None
    return parts[3], parts[4]


def parse_payload(raw_payload, expected_channels):
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Dropping message: invalid JSON")
        return None

    required_keys = {"timestamp", "sample_rate_hz", "channels"}
    if not required_keys.issubset(data):
        logger.warning("Dropping message: missing keys %s", required_keys - set(data))
        return None

    channels = data["channels"]
    if not all(ch in channels for ch in expected_channels):
        logger.warning(
            "Dropping message: expected channels %s, got %s",
            expected_channels,
            list(channels.keys()),
        )
        return None

    try:
        ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Dropping message: unparseable timestamp %r", data["timestamp"])
        return None

    return {
        "ts": ts,
        "sample_rate_hz": float(data["sample_rate_hz"]),
        "channels": channels,
    }


async def handle_message(pool, topic, raw_payload):
    parsed_topic = parse_topic(topic)
    if parsed_topic is None:
        logger.warning("Dropping message: unrecognized topic %r", topic)
        return

    machine_id, sensor_type = parsed_topic

    table_entry = TABLE_MAP.get(sensor_type)
    if table_entry is None:
        logger.warning(
            "Dropping message: unknown sensor_type %r on topic %r", sensor_type, topic
        )
        return

    table, channel_cols = table_entry

    row = parse_payload(raw_payload, channel_cols)
    if row is None:
        return
    row["machine_id"] = (
        machine_id  # the topic path is the authority for machine identity
    )

    try:
        await insert_window(pool, table, channel_cols, row)
        logger.info(
            "Inserted window: machine=%s table=%s ts=%s",
            machine_id,
            table,
            row["ts"].isoformat(),
        )
    except asyncpg.PostgresError:
        logger.exception("DB insert failed for machine=%s table=%s", machine_id, table)


async def consume_forever(pool):
    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                await client.subscribe(TOPIC_FILTER)
                logger.info(
                    "Subscribed to %s on %s:%d", TOPIC_FILTER, MQTT_HOST, MQTT_PORT
                )

                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload
                    if isinstance(payload, (bytearray, memoryview)):
                        payload = bytes(payload)
                    # Fire-and-forget: a slow insert must not block the MQTT receive loop.
                    asyncio.create_task(handle_message(pool, topic, payload))

        except aiomqtt.MqttError as e:
            logger.error(
                "MQTT connection lost (%s); reconnecting in %ds",
                e,
                RECONNECT_DELAY_SECONDS,
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)


async def main():
    pool = await create_pool()
    try:
        await consume_forever(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    # On Windows, the default ProactorEventLoop lacks add_reader/add_writer,
    # which aiomqtt (via paho-mqtt) needs. Force the selector loop instead.
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())

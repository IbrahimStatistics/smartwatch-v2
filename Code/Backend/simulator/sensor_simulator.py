"""SmartWatch telemetry simulator: replays dataset recordings over MQTT.

Loads one healthy/fault recording per run, slices it into 1-second windows,
and publishes each window to the Mosquitto broker at simulated real-time
pacing, so the consumer and database see a live sensor stream.

Run from the Backend/ folder (so `loader` resolves as a package):
    python -m simulator.sensor_simulator [--health rs] [--torque torque05] [--loop]
"""

import argparse
import json
import time
from datetime import UTC, datetime

import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from loader import get_sample_rate, load_signal

RECORDING_DURATION_SECONDS = 18
CURRENT_CHANNELS = ["Ia", "Ib", "Ic"]
VIBRATION_CHANNELS = ["Vib_axial", "Vib_base", "Vib_carc", "Vib_acpe", "Vib_acpi"]

MQTT_BROKER = "localhost"
MQTT_PORT = 1883


def preview(arr, n=4):
    """Return a short string preview of an array's first n values plus basic stats."""
    a = np.asarray(arr)
    head = ", ".join(f"{v:.4f}" for v in a[:n])
    return f"[{head}, ...] (n={len(a)}, min={a.min():.3f}, max={a.max():.3f}, mean={a.mean():.4f})"


def build_topic(factory_id, line_id, machine_id, sensor_group):
    return f"smartwatch/{factory_id}/{line_id}/{machine_id}/{sensor_group}"


def slice_window(signal, sample_rate, window_index, window_duration_s):
    start = int(window_index * window_duration_s * sample_rate)
    end = int((window_index + 1) * window_duration_s * sample_rate)
    return signal[start:end]


def run_simulator(
    health_condition,
    torque_level,
    device_id,
    factory_id,
    line_id,
    machine_id,
    window_duration_s=1.0,
    speed=1.0,
):

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_BROKER, MQTT_PORT)

    current_signals = {
        ch: load_signal(health_condition, torque_level, ch) for ch in CURRENT_CHANNELS
    }
    vibration_signals = {
        ch: load_signal(health_condition, torque_level, ch) for ch in VIBRATION_CHANNELS
    }

    fs_current = get_sample_rate(current_signals["Ia"].shape[0])
    fs_vibration = get_sample_rate(vibration_signals["Vib_axial"].shape[0])

    num_windows = int(RECORDING_DURATION_SECONDS / window_duration_s)

    print(f"Starting simulation: {device_id} | {health_condition} | {torque_level}")
    print(
        f"Current fs={fs_current:.2f}Hz | Vibration fs={fs_vibration:.2f}Hz | {num_windows} windows"
    )

    for w in range(num_windows):
        timestamp = datetime.now(UTC).isoformat()

        current_payload = {
            "device_id": device_id,
            "timestamp": timestamp,
            "sample_rate_hz": round(fs_current, 2),
            "window_duration_ms": int(window_duration_s * 1000),
            "channels": {
                ch: slice_window(sig, fs_current, w, window_duration_s).tolist()
                for ch, sig in current_signals.items()
            },
            "health_condition_sim": health_condition,
            "torque_level_sim": torque_level,
        }

        print(f"  Window {w + 1}/{num_windows} | {timestamp}")
        print(f"    Ia:        {preview(current_payload['channels']['Ia'])}")

        client.publish(
            build_topic(factory_id, line_id, machine_id, "current"),
            json.dumps(current_payload),
        )

        vibration_payload = {
            "device_id": device_id,
            "timestamp": timestamp,
            "sample_rate_hz": round(fs_vibration, 2),
            "window_duration_ms": int(window_duration_s * 1000),
            "channels": {
                ch: slice_window(sig, fs_vibration, w, window_duration_s).tolist()
                for ch, sig in vibration_signals.items()
            },
            "health_condition_sim": health_condition,
            "torque_level_sim": torque_level,
        }
        print(f"    Vib_axial: {preview(vibration_payload['channels']['Vib_axial'])}")

        client.publish(
            build_topic(factory_id, line_id, machine_id, "vibration"),
            json.dumps(vibration_payload),
        )

        print(f"  Window {w + 1}/{num_windows} published at {timestamp}")
        time.sleep(window_duration_s / speed)

    client.disconnect()
    print("Simulation complete.")


if __name__ == "__main__":
    load_dotenv()  # picks up DATASET_DIR from Backend/.env before the loader runs
    parser = argparse.ArgumentParser(description="SmartWatch telemetry simulator")
    parser.add_argument("--health", default="rs")
    parser.add_argument("--torque", default="torque05")
    parser.add_argument("--device-id", default="sim-motor-01")
    parser.add_argument("--factory", default="factory1")
    parser.add_argument("--line", default="line1")
    parser.add_argument("--machine", default="motorA")
    parser.add_argument("--window-ms", type=float, default=1000)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Repeat the recording continuously until Ctrl+C, instead of running once.",
    )
    args = parser.parse_args()

    run_kwargs = dict(
        health_condition=args.health,
        torque_level=args.torque,
        device_id=args.device_id,
        factory_id=args.factory,
        line_id=args.line,
        machine_id=args.machine,
        window_duration_s=args.window_ms / 1000,
        speed=args.speed,
    )

    if args.loop:
        print("Looping continuously — press Ctrl+C to stop.")
        try:
            while True:
                run_simulator(**run_kwargs)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        run_simulator(**run_kwargs)

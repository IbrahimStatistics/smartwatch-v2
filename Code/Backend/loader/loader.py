"""
Load raw motor signals from the IEEE DataPorts .mat dataset.
The dataset ships as MATLAB v7.3 .mat files. Those are the HDF5 Files under the hood, so we read them with h5py -- scipy.io.loadmat only understands older .mat formats.

File layout inside each .mat file (HDF5 gruops, like folders):

    struct_rs_R1.mat
    - rs/torque05/Ia -> (10, 1) array of "object references"

The channel dataset holds one object reference per repetition (a point where that repetition's signal actuallu livesi n the file). Loading therefore two steps: read the reference, then dereference it with f[ref].

Where the files live is configuration, not code: set the DATASET_DIR environment variable (e.g. in a .env file). This module never contains a hardcoded path to one developer's machine.
"""

import os
from pathlib import Path

import h5py
import numpy as np
from dotenv import load_dotenv

RECORDING_DURATION_SECONDS = 18  # as per the dataset docs
REPETITIONS_PER_CONDITION = 10

CURRENT_VOLTAGE_CHANNELS = frozenset({"Ia", "Ib", "Ic", "Va", "Vb", "Vc", "Trigger"})
VIBRATION_CHANNELS = frozenset(
    {"Vib_axial", "Vib_base", "Vib_carc", "Vib_acpe", "Vib_acpi"}
)


def _dataset_dir() -> Path:
    """
    Resolve the dataset location from the environment.

    Raise a clear error telling the user exactly what to set,
    instead of failing later with a confusing FileNotFoundError.
    """
    raw = os.environ.get("DATASET_DIR")

    if not raw:
        raise RuntimeError(
            "DATASET_DIR is not set. Point it at the folder holding "
            "the .mat files, e.g. DATASET_DIR=C:/data/5.Dataset. "
            "Tip: put it in a .env file and call load_dotenv() "
            "before using the loader."
        )

    path = Path(raw).expanduser()

    if not path.is_dir():
        raise NotADirectoryError(f"DATASET_DIR is not a valid directory: {path}")

    return path


def load_signal(
    health_condition: str,
    torque_level: str,
    channel: str,
    repetition: int = 0,
    file_suffix: str = "R1",
) -> np.ndarray:
    """Load one signal channel as a 1D numpy array.

    Parameters
    ----------
    health_condition : 'rs' (healthy) or 'r1b'..'r4b' (1-4 broken rotor bars)
    torque_level     : 'torque05' .. 'torque40' (0.5 Nm .. 4.0 Nm)
    channel          : e.g. 'Ia', 'Vib_axial' (see channel sets above)
    repetition       : 0 .. 9 (ten recordings per condition)
    file_suffix      : matches the filename pattern, e.g. struct_rs_R1.mat
    """
    if not 0 <= repetition < REPETITIONS_PER_CONDITION:
        raise ValueError(
            f"repetition must be 0..{REPETITIONS_PER_CONDITION - 1}, got {repetition}"
        )

    file_path = _dataset_dir() / f"struct_{health_condition}_{file_suffix}.mat"
    if not file_path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    # 'with' closes the HDF5 file automatically, like RAII in C++.
    with h5py.File(file_path, "r") as f:
        group = f[health_condition][torque_level]
        if channel not in group:
            raise KeyError(
                f"Channel '{channel}' not found. Available: {list(group.keys())}"
            )
        ref = group[channel][repetition, 0]  # an object reference: a pointer, not data
        data = f[ref][:]  # dereference it and read the full array

    return np.asarray(data).flatten()  # (N, 1) column -> 1D


def get_sample_rate(num_samples: int) -> float:
    """Derive the sample rate from the sample count and the known 18 s duration.

    Do NOT hardcode sample rates: current and vibration channels were recorded
    at different rates. Always compute this from the real loaded array.
    """
    return num_samples / RECORDING_DURATION_SECONDS


def get_time_axis(num_samples: int) -> np.ndarray:
    """Build a time axis in seconds, derived from the actual sample count."""
    return np.arange(num_samples) / get_sample_rate(num_samples)


def channel_category(channel: str) -> str:
    """Return 'current_voltage' or 'vibration' (useful for routing/logging)."""
    if channel in CURRENT_VOLTAGE_CHANNELS:
        return "current_voltage"
    if channel in VIBRATION_CHANNELS:
        return "vibration"
    raise ValueError(f"Unknown channel: {channel}")


if __name__ == "__main__":
    # Manual smoke test: `python -m loader.loader` from the Backend folder.
    # Needs DATASET_DIR to point at the real .mat files.
    load_dotenv()
    for ch in ["Ia", "Vib_axial", "Vib_base", "Ic"]:
        signal = load_signal(
            health_condition="rs", torque_level="torque05", channel=ch, repetition=0
        )
        fs = get_sample_rate(signal.shape[0])
        print(
            f"{ch:12s} | category={channel_category(ch):15s} | "
            f"samples={signal.shape[0]:>8} | derived sample rate={fs:.2f} Hz"
        )

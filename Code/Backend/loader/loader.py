'''
Load raw motor signals from the IEEE DataPorts .mat dataset.
The dataset ships as MATLAB v7.3 .mat files. Those are the HDF5 Files under the hood, so we read them with h5py -- scipy.io.loadmat only understands older .mat formats.

File layout inside each .mat file (HDF5 gruops, like folders):

    struct_rs_R1.mat
    - rs/torque05/Ia -> (10, 1) array of "object references"

The channel dataset holds one object reference per repetition (a point where that repetition's signal actuallu livesi n the file). Loading therefore two steps: read the reference, then dereference it with f[ref].

Where the files live is configuration, not code: set the DATASET_DIR environment variable (e.g. in a .env file). This module never contains a hardcoded path to one developer's machine.
'''

import os
from pathlib import Path

import h5py 
import numpy as np
from dotenv import load_dotenv

RECORDING_DURATION_SECNODS = 18 #as per the dataset docs
REPETITIONS_PER_CONDITION = 10

CURRENT_VOLTAGE_CHANNELS = frozenset({"Ia", "Ib", "Ic", "Va", "Vb", "Vc", "Trigger"})
VIBRATION_CHANNELS = frozenset({"Vib_axial", "Vib_base", "Vib_carc", "Vib_acpe", "Vib_acpi"})


import os
from pathlib import Path


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
        raise NotADirectoryError(
            f"DATASET_DIR is not a valid directory: {path}"
        )

    return path


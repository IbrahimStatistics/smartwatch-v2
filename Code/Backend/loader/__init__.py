# Read raw motor signals from the IEEE DataPort broken-rotor-bar dataset.

from .loader import channel_category, get_sample_rate, get_time_axis, load_signal
__all__ = ["channel_category", "get_sample_rate", "get_time_axis", "load_signal"]
"""contract/telemetry.py: single source of truth for the MQTT wire contract.

Every producer (simulator) and consumer (ingestion) imports from here.
Nothing else in the codebase may hardcode topic layout, channel names, or
payload keys. If the contract changes, it changes in this file only.

Topic layout:
    smartwatch/<factory>/<line>/<machine>/<sensor_group>
    e.g. smartwatch/factory1/line1/motorA/current
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TOPIC_ROOT: Final = "smartwatch"
TOPIC_FILTER: Final = f"{TOPIC_ROOT}/+/+/+/+"
_FORBIDDEN_SEGMENT_CHARS: Final = frozenset("/+#")


@dataclass(frozen=True)
class SensorGroup:
    """One family of channels that travel together and land in one table."""

    name: str
    table: str
    channels: tuple[str, ...]


SENSOR_GROUPS: Final[dict[str, SensorGroup]] = {
    "current": SensorGroup(
        name="current",
        table="telemetry_current",
        channels=("Ia", "Ib", "Ic"),
    ),
    "vibration": SensorGroup(
        name="vibration",
        table="telemetry_vibration",
        channels=("Vib_axial", "Vib_base", "Vib_carc", "Vib_acpe", "Vib_acpi"),
    ),
}


class TopicParts(NamedTuple):
    factory: str
    line: str
    machine: str
    sensor_group: str

    @property
    def machine_key(self) -> str:
        """Globally unique machine identity: factory/line/machine."""
        return f"{self.factory}/{self.line}/{self.machine}"


def _check_segment(label: str, value: str) -> None:
    if not value:
        raise ValueError(f"topic segment '{label}' must not be empty")
    bad = _FORBIDDEN_SEGMENT_CHARS.intersection(value)
    if bad:
        raise ValueError(
            f"topic segment '{label}'={value!r} contains forbidden characters {sorted(bad)}"
        )


def build_topic(factory: str, line: str, machine: str, sensor_group: str) -> str:
    """Build a publish topic. Raises ValueError on anything the contract forbids."""
    if sensor_group not in SENSOR_GROUPS:
        raise ValueError(
            f"unknown sensor_group {sensor_group!r}; expected one of {sorted(SENSOR_GROUPS)}"
        )
    for label, value in (("factory", factory), ("line", line), ("machine", machine)):
        _check_segment(label, value)
    return f"{TOPIC_ROOT}/{factory}/{line}/{machine}/{sensor_group}"


def parse_topic(topic: str) -> TopicParts:
    """Parse a received topic. Raises ValueError with a specific reason."""
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != TOPIC_ROOT:
        raise ValueError(
            f"topic {topic!r} does not match {TOPIC_ROOT}/<f>/<l>/<m>/<group>"
        )
    _, factory, line, machine, sensor_group = parts
    if sensor_group not in SENSOR_GROUPS:
        raise ValueError(
            f"unknown sensor_group {sensor_group!r}; expected one of {sorted(SENSOR_GROUPS)}"
        )
    for label, value in (("factory", factory), ("line", line), ("machine", machine)):
        _check_segment(label, value)
    return TopicParts(factory, line, machine, sensor_group)


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class TelemetryWindow(BaseModel):
    """One window of raw samples, as sent over MQTT.

    extra="forbid" is deliberate: if a producer adds or renames a field, the
    consumer must fail loudly instead of silently ignoring it.
    """

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)
    timestamp: datetime
    sample_rate_hz: float = Field(gt=0)
    window_duration_ms: int = Field(gt=0)
    channels: dict[str, list[FiniteFloat]]
    health_condition_sim: str | None = None
    torque_level_sim: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _channels_consistent(self) -> TelemetryWindow:
        if not self.channels:
            raise ValueError("channels must not be empty")
        lengths = {name: len(samples) for name, samples in self.channels.items()}
        if 0 in lengths.values():
            raise ValueError(f"channels contain an empty signal: {lengths}")
        if len(set(lengths.values())) != 1:
            raise ValueError(f"channel lengths differ within one window: {lengths}")
        return self

    def check_group(self, sensor_group: str) -> None:
        """Verify the channel set matches exactly what the topic's group requires."""
        expected = set(SENSOR_GROUPS[sensor_group].channels)
        actual = set(self.channels)
        if actual != expected:
            raise ValueError(
                f"channels for {sensor_group!r} must be {sorted(expected)}, "
                f"got missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
            )

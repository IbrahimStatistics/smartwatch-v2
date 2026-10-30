CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE telemetry_current (
    machine_id TEXT NOT NULL,
    time TIMESTAMPTZ NOT NULL,
    sample_rate_hz DOUBLE PRECISION,
    "Ia" DOUBLE PRECISION [] NOT NULL,
    "Ib" DOUBLE PRECISION [] NOT NULL,
    "Ic" DOUBLE PRECISION [] NOT NULL,
    PRIMARY KEY (machine_id, time)
);
SELECT create_hypertable('telemetry_current', 'time');
CREATE TABLE telemetry_vibration (
    machine_id TEXT NOT NULL,
    time TIMESTAMPTZ NOT NULL,
    sample_rate_hz DOUBLE PRECISION,
    "Vib_axial" DOUBLE PRECISION [] NOT NULL,
    "Vib_base" DOUBLE PRECISION [] NOT NULL,
    "Vib_carc" DOUBLE PRECISION [] NOT NULL,
    "Vib_acpe" DOUBLE PRECISION [] NOT NULL,
    "Vib_acpi" DOUBLE PRECISION [] NOT NULL,
    PRIMARY KEY (machine_id, time)
);
SELECT create_hypertable('telemetry_vibration', 'time');
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
# SmartWatch Manager v2 — Phase 1: Ingestion Pipeline

End-to-end IIoT ingestion pipeline for induction motor condition monitoring.
Phase 1 covers dataset → MQTT → TimescaleDB. The API, dashboard, and ML
fault detection come in later phases.

## Architecture

MATLAB .mat recordings → loader → simulator → MQTT (Mosquitto)
→ async consumer → TimescaleDB hypertables

## Components

- `Code/Backend/loader/` — reads IEEE DataPort .mat files (HDF5) with h5py;
  sample rates derived from the data (current ≈ 55,611 Hz, vibration 8,528 Hz).
- `Code/Backend/simulator/` — replays recordings as 1-second MQTT windows.
- `Code/Backend/database/` — Mosquitto + TimescaleDB via Docker Compose.
- `Code/Backend/consumer/` — async MQTT subscriber; validates and inserts
  windows into hypertables.

## Quickstart

```bash
cd Code
python -m venv .venv
.venv\Scripts\activate
cd Backend
pip install -r requirements.txt
copy .env.example .env   # fill in DATASET_DIR
cd database
docker compose up -d
Get-Content schema.sql | docker exec -i timescaledb psql -U postgres -d iiot
cd ..
python -m consumer.consumer
python -m simulator.sensor_simulator
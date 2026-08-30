# Running the MVP locally

This document describes the minimal steps to run the completed MVP locally. The
MVP demonstrates the end-to-end pipeline using synthetic/demo data (no external
oceanographic downloads or GPU required).

Prerequisites
- Python 3.11+ (the backend requirements pin some modern libs)
- Node/npm to run the frontend (optional for the API-only demo)

Steps
1. Create a virtual environment and install backend deps

```bash
cd "Marine Oil Spill Detection"
python -m venv backend/.venv
source backend/.venv/bin/activate    # or backend\.venv\Scripts\activate on Windows
pip install -U pip
pip install -r backend/requirements.txt
```

2. Generate demo data

```bash
python scripts/generate_demo_data.py
```

This writes JSON to `data/processed/` including `demo_slicks.json`,
`demo_tracks.json`, and `demo_reports.json`.

3. Run the API

```bash
uvicorn app.main:app --reload
```

4. Try the demo endpoints (example)

- List slicks:
  GET http://127.0.0.1:8000/api/v1/detections/demo

- Backtrack a slick (use a slick id from the list):
  GET http://127.0.0.1:8000/api/v1/detections/demo/{slick_id}/backtrack

- Recompute attribution for a slick:
  GET http://127.0.0.1:8000/api/v1/attribution/demo/{slick_id}/compute

Frontend
The frontend snapshot uses committed demo JSON under `frontend/api/data/` and can
be run with:

```bash
cd frontend
npm install
npm run dev
```

Notes
- The backtrack engine uses a synthetic analytic current field for fast,
  deterministic demo runs. For production, replace `app.core.drift.synthetic_current`
  with a gridded-ocean current lookup and a higher-order integrator (RK4).

# Marine Oil Spill Detection & Vessel Attribution

An end-to-end automated pipeline for **Smart India Hackathon (SIH)** that:
1. Detects oil slicks from **SAR + optical satellite imagery** (`Swin-UPerNet`, mIoU **0.840**).
2. Classifies **oil type** from histogram/spectral analysis of spill pixels.
3. Monitors oil/chemical carriers in real time, and when a spill is detected,
   identifies the **responsible vessel** with **location, distance from spill,
   oil type, and correlation score**.
4. Shows **existing (historical) spills** and **live alerts** on a geospatial dashboard.

> **Key differentiator:** the AIS module includes a **cybersecurity layer**
> (spoofing / anomaly detection) that filters untrustworthy signals before
> attribution.

---

## Research-Backed Model Choice

| Model          | Architecture | mIoU  |
|----------------|--------------|-------|
| DeepLabV3+     | CNN          | 0.740 |
| Mask2Former    | Transformer  | 0.804 |
| **Swin-UPerNet** | **Transformer** | **0.840 ⭐** |

Swin-UPerNet is selected as the primary segmentation model (best mIoU). See
`docs/technical-approach.md` for the full system + sequence diagrams.

---

## Project Structure

```
Marine Oil Spill Detection/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint
│   │   ├── config.py               # location-independent settings
│   │   ├── api/                    # REST routes (+ Vercel-compatible demo data)
│   │   ├── core/                   # schemas, utils
│   │   ├── detection/              # Phase 1: SAR → slick + oil type
│   │   ├── ais/                    # Phase 2: spoof/anomaly + clean tracks
│   │   ├── attribution/            # Phase 3: vessel correlation card
│   │   └── models/                 # Swin-UPerNet / DeepLabV3+ factory
│   ├── tests/                      # pytest suite
│   └── requirements.txt
├── frontend/                       # React + Vite + MapLibre dashboard (Vercel-deployable)
│   └── api/                        # Vercel serverless functions + committed data snapshot
├── scripts/
│   ├── generate_demo_data.py       # synthetic slicks + AIS (offline demo)
│   ├── monitor_service.py          # real-time monitoring loop (local)
│   └── train_detector.py           # Phase 1 training entrypoint
├── data/raw, data/processed
├── docs/technical-approach.md      # diagrams
└── README.md
```

---

## Setup (Windows / Python 3.14)

### Backend
```powershell
cd "Marine Oil Spill Detection"
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -U pip
backend\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" pydantic pydantic-settings numpy pandas pytest httpx python-dotenv

# Tests
backend\.venv\Scripts\python.exe -m pytest backend\tests -v

# Demo data
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe scripts\generate_demo_data.py

# Run the API (localhost)
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# Docs: http://127.0.0.1:8000/docs
```

### Real-time monitor (localhost, live monitoring)
```powershell
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe scripts\monitor_service.py          # loop
backend\.venv\Scripts\python.exe scripts\monitor_service.py --once   # single pass
```
Writes live state to `data/processed/live_state.json`.

### Frontend
```powershell
cd frontend
"C:\path\to\npm.cmd" install
"C:\path\to\npm.cmd" run dev    # http://localhost:5173 (Vite proxies /api -> :8000)
```

> **Python 3.14:** older pins of pydantic/numpy lack wheels. Use the unpinned
> installs above. For `torch`/`mmsegmentation` (training only) prefer Python 3.11/3.12.

---

## Vessel Correlation Output (per detected spill)

The attribution engine produces a human-readable **correlation card**:

```
Likely vessel:          MT SUSPECT-ONE (MMSI 413000111)
Vessel type:            tanker
Correlation score:      89%
Distance from spill:    1.09 km
Track intersection:     Yes
Vessel speed:           0.8 kn (near-0 = discharge signature)
Vessel direction:       160.0 deg
Oil type:               crude-oil          ← histogram/spectral analysis
```

Scoring fuses **proximity** (distance from spill), **trajectory** (temporal +
spatial consistency), and **behavior** (near-zero speed = discharge signature),
weighted 50 / 30 / 20.

---

## Deployment (GitHub + Vercel)

Vercel cannot run the heavy ML model or long-running AIS streams, so the system
is split:

- **Cloud (Vercel)** hosts the frontend + thin serverless API. It serves a
  committed **data snapshot** (`frontend/api/data/*.json`) so the deployed site is
  fully functional.
- **Local / VM** runs the heavy pipeline and the real-time monitor, and pushes
  results to a hosted DB (e.g. **Supabase**) for production.

### Deploy steps
1. Push the repo to GitHub.
2. In Vercel, import the repo and set **Root Directory** → `Marine Oil Spill Detection/frontend`.
3. Vercel auto-detects Vite; it builds `dist/` and deploys the `api/` serverless
   functions alongside the frontend.
4. Re-run `scripts/generate_demo_data.py` and refresh `frontend/api/data/*.json`
   whenever you want to update the deployed demo data.

### Scale to Supabase (optional production path)
- Add tables: `slicks`, `tracks`, `attribution_scores`, `events`.
- Point `monitor_service.py` at Supabase (Postgres) instead of the local file.
- Add Supabase RLS + a service-role key for the Vercel functions to read live
  reports in real time.

---

## API Overview (localhost)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/v1/ais/live` | Live moving vessel positions (MarineTraffic-style map) |
| GET | `/api/v1/detections/demo` | Live detected slicks (with oil type) |
| GET | `/api/v1/detections/historical` | Existing (historical) spills |
| GET | `/api/v1/attribution/demo` | Attribution reports (correlation cards) |
| POST | `/api/v1/attribution/{slick_id}` | Trigger attribution for a slick |

---

## SIH Demo Strategy

1. **Live satellite → mask**: run Phase 1 (Swin-UPerNet) on a real SAR scene → overlay.
2. **Real-time monitor**: show `monitor_service.py` polling and emitting alerts.
3. **Spoof-attack demo**: inject a fake AIS signal → IDS filters it, attribution stays trustworthy *(standout)*.
4. **Correlation card**: one click shows suspect vessel + distance + oil type + confidence.

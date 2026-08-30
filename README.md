# Marine Oil Spill Detection & Vessel Attribution

An end-to-end automated pipeline for **SIH** that:
1. Detects oil slicks from **SAR/optical satellite imagery** (deep learning).
2. Models **ocean drift** (forward & hindcast) to estimate slick origin.
3. Correlates with **AIS data** to attribute the spill to the responsible vessel.
4. Visualizes results on a **geospatial dashboard** with confidence scores.

> The AIS module includes a **cybersecurity layer** (spoofing/anomaly detection)
> that filters untrustworthy signals before attribution — a key differentiator.

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint
│   │   ├── config.py               # Settings (.env driven)
│   │   ├── api/                    # REST routes
│   │   │   ├── detections.py       # Phase 1 routes
│   │   │   ├── attribution.py      # Phase 3 routes
│   │   │   └── *_demo.py           # Scaffolding-only demo routes
│   │   ├── core/
│   │   │   ├── schemas.py          # Pydantic domain models (pipeline contracts)
│   │   │   └── utils.py            # geo math, ids, time
│   │   ├── detection/              # Phase 1: SAR → slick detection
│   │   │   ├── preprocess.py       # calibration, land-mask, tiling
│   │   │   └── service.py          # orchestration + geometry
│   │   ├── ais/                    # Phase 2: AIS anomaly + clean tracks
│   │   │   ├── service.py          # spoof/anomaly detection, track building
│   │   │   └── store.py            # in-memory track store (→ DB later)
│   │   ├── attribution/            # Phase 3: vessel attribution scoring
│   │   │   └── service.py
│   │   └── models/                 # ML model definitions
│   │       └── unet.py             # DeepLabV3+ + contrastive head
│   ├── tests/
│   │   └── test_pipeline.py        # 5 passing tests
│   └── requirements.txt
├── frontend/                       # React + Vite + MapLibre dashboard
├── scripts/
│   ├── generate_demo_data.py       # synthetic data for scaffolding
│   └── train_detector.py           # Phase 1 training entrypoint
├── data/
│   ├── raw/                        # sar/, optical/, ais/
│   └── processed/                  # demo outputs + derived products
├── notebooks/                      # EDA & model experiments
├── config/                         # runtime configs
└── docs/                           # design & SIH notes
```

---

## Setup (tested on Windows / Python 3.14)

### Backend
```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -U pip
backend\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" pydantic pydantic-settings numpy pandas pytest httpx python-dotenv

# Run tests
backend\.venv\Scripts\python.exe -m pytest backend\tests -v

# Generate demo data (synthetic slicks + AIS so the pipeline runs offline)
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe scripts\generate_demo_data.py

# Start API
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# Docs: http://127.0.0.1:8000/docs
```

> **Note on Python 3.14:** older pins of `pydantic`/`numpy` lack wheels. Use the
> unpinned installs above (latest). For `torch`/`rasterio` (training only),
> prefer a Python 3.11/3.12 environment until wheels ship for 3.14.

### Frontend
```powershell
cd frontend
# use npm.cmd on systems where the .ps1 shim is blocked by execution policy
"C:\path\to\npm.cmd" install
"C:\path\to\npm.cmd" run dev      # http://localhost:5173 (proxies /api → :8000)
```

---

## Verify End-to-End

1. Start backend (`uvicorn app.main:app --port 8000`).
2. Generate demo data (above).
3. `http://127.0.0.1:8000/api/v1/detections/demo` → detected slick JSON.
4. `http://127.0.0.1:8000/api/v1/attribution/demo` → ranks suspect vessel with
   confidence (demonstrates the full attribution path offline).
5. `cd frontend && npm run dev` → dashboard map showing the slick and top suspect.

---

## SIH Roadmap (Build Sequence)

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | **Detection MVP** — SAR → segmentation mask | ✅ scaffold / ⏳ train |
| 2 | **AIS ingest + anomaly/spoof filter** | ✅ logic + tests |
| 3 | **Attribution scoring + correlation** | ✅ logic + tests |
| 4 | **Dashboard integration** (map + confidence) | ✅ scaffold |
| 5 | **Drift modelling** forward + hindcast | ⏳ next |
| 6 | **GenAI augmentation + transfer learning** | ⏳ training |
| 7 | **Real-time playback + demo story** | ⏳ |

### Recommended next work
- Download a public Sentinel-1 dataset, wire the real SAR loader in
  `detection/preprocess.py`, then train `scripts/train_detector.py`.
- Replace the in-memory track store with PostGIS + partitioned AIS tables.
- Implement the drift model (OpenDrift or GNOME-style) for origin hindcasting.

---

## Demo Strategy (for Judges)
1. **Live satellite → mask**: run Phase 1 on a real SAR scene, show the overlay.
2. **Simulated AIS playback**: replay a discharge event; vessel "goes dark".
3. **Spoof-attack demo**: inject a fake AIS signal mid-demo → IDS filters it,
   attribution stays trustworthy. *(standout feature)*
4. **One-click case card**: emit the full evidence packet (spill + suspect +
   confidence) for enforcement.

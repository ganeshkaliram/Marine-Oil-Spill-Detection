# Architecture

## Pipeline Overview

```
DATA INGESTION ─► PREPROCESSING ─► PHASE 1 DETECTION ─► PHASE 2 AIS ─► PHASE 3 ATTRIBUTION ─► PHASE 4 UI
   SAR/optical         calib/land-mask     DeepLabV3+         spoof/anomaly      spatiotemporal      map + confidence
   + AIS               clean/tile          slicks             clean tracks        scoring            case cards
```

## Stage Contracts (see backend/app/core/schemas.py)

- **Phase 1** → `SlickDetection` (geometry, confidence, characterization)
- **Phase 2** → `VesselTrack` (points, trust_score, anomalies)
- **Phase 3** → `AttributionReport` (ranked suspect vessels + confidence)

## Key Design Decisions

1. **Uncertainty-first**: every stage outputs distributions/confidence, not
   point answers — propagated to attribution for honest scoring.
2. **AIS trust gating**: vessels below `AIS_SPOOF_SCORE_THRESHOLD` are excluded
   from attribution, preventing spoofed data from yielding false positives.
3. **Decoupled routes**: demo routes are namespaced separately and registered
   before parameterised routes to avoid path capture.
4. **DI-friendly services**: detection/AS/attribution services take injectable
   collaborators so they are unit-testable without heavy model deps.

## Data Flow for a Single Event

1. New SAR granule arrives → preprocess → 3 channels (VV, VH, VV/VH).
2. DeepLabV3+ segmentation → mask → connected components → `SlickDetection`.
3. AIS stream filtered by `AisAnomalyDetector` → `VesselTrack`s with trust.
4. `AttributionService` correlates slick window × tracks → scored suspects.
5. API serialises results → dashboard renders map + confidence meters.

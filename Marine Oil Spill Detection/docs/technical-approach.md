# Technical Approach Diagram

> Mermaid source. Renders natively on GitHub (and in VS Code / GitHub Markdown).
> A plain-text fallback is included at the bottom.

## Model Selection (research-backed)

Benchmark on high-resolution optical satellite data for oil-spill segmentation
(**mIoU = mean Intersection over Union**, higher is better):

| Model        | Architecture | mIoU  |
|--------------|--------------|-------|
| DeepLabV3+   | CNN          | 0.740 |
| Mask2Former  | Transformer  | 0.804 |
| **Swin-UPerNet** | **Transformer** | **0.840 ⭐** |

> **Decision:** Use **Swin-UPerNet** as the primary segmentation model — it
> achieved the highest mIoU (0.840). Complement with optical + SAR fusion and
> **histogram analysis** of predicted spill pixels for **oil-type classification**.

## System Architecture

```mermaid
flowchart TB
    subgraph DATA["DATA SOURCES"]
        AIS["AIS FEEDS<br/>(MarineCadastre / synthetic)"]
        SAR["SENTINEL-1 SAR<br/>(dual-pol VV+VH)"]
        OPT["OPTICAL EO<br/>(Sentinel-2, optional)"]
    end

    subgraph LOCAL["LOCAL PIPELINE (your machine / VM)"]
        ING["INGEST & PREPROCESS<br/>geo-correct · land-mask · denoise"]
        DET["PHASE 1 · SPILL DETECTION<br/>Swin-UPerNet (Transformer)<br/>mIoU 0.840 ⭐<br/>+ oil-type (histogram) class"]
        AISAN["PHASE 2 · VESSEL ANALYTICS<br/>spoof/anomaly detection<br/>clean tracks + trust score"]
        ATTR["PHASE 3 · ATTRIBUTION<br/>likely vessel · correlation %<br/>distance from spill · track intersection<br/>vessel speed/direction · oil-type"]
        MON["REAL-TIME MONITOR<br/>poll AIS + SAR on timer<br/>flag live spills & vessels"]
    end

    subgraph CLOUD["CLOUD (Vercel + Supabase)"]
        DB[("SUPABASE Postgres<br/>slicks · tracks · reports<br/>historical spills")]
        API["VERCEL API (thin)<br/>read reports · serve GeoJSON"]
        UI["VERCEL FRONTEND<br/>React + MapLibre<br/>existing + live spills<br/>suspect vessel cards"]
    end

    AIS --> ING
    SAR --> ING
    OPT --> ING

    ING --> DET
    ING --> AISAN
    DET --> ATTR
    AISAN --> ATTR
    ATTR --> MON
    MON --> DB

    DB <--> API
    API --> UI

    HST["HISTORICAL SPILLS<br/>(preloaded GeoJSON)"] --> DB
```

## Real-Time Monitoring Loop

```mermaid
flowchart LR
    T[Timer every N minutes] --> P[Pull new AIS + SAR scene]
    P --> D[Detect spills]
    P --> A[Analyze vessels]
    D --> M{Spill found?}
    A --> M
    M -- no --> T
    M -- yes --> ATT[Attribute vessel<br/>lat/long · distance · oil-type]
    ATT --> WRITE[Write to Supabase]
    WRITE --> U[UI shows live alert]
    U --> T
```

## Component Data Flow (single event)

```mermaid
sequenceDiagram
    participant Monitor
    participant Detection
    participant Attribution
    participant DB as Supabase
    participant UI as Map Dashboard

    Monitor->>Detection: SAR scene
    Detection->>Attribution: SlickDetection (geoms, conf)
    Monitor->>Attribution: cleaned AIS tracks
    Attribution->>Attribution: score vessels (proximity, distance, oil-type)
    Attribution->>DB: AttributionReport (top suspect + confidence)
    DB-->>UI: live refresh
    UI->>UI: overlay existing + live spills, suspect vessel
```

## Plain-Text Fallback

```
DATA SOURCES                          LOCAL PIPELINE                        CLOUD
┌──────────────┐          ┌──────────────────────────────────────┐   ┌─────────────────────┐
│ AIS feeds    │──────┐   │ INGEST & PREPROCESS                  │   │ SUPABASE Postgres   │
│ SAR S1 VV+VH │──────┼──►│ geo-correct · land-mask · denoise   │   │ slicks·tracks·reports│
│ Optical EO   │──────┘   │ ──────────────────────────────────── │   └──────────┬──────────┘
└──────────────┘          │ PHASE1 Swin-UPerNet (mIoU 0.840)    │              │
                          │        + oil-type histogram          │              │
                          │ PHASE2 vessel AIS (spoof+trust)      │              │
                          │ PHASE3 attribution (likely vessel,   │              │
                          │        corr %, distance, intersection)│             │
                          │ ──────────────────────────────────── │              ▼
                          │ REAL-TIME MONITOR (timer → DB)       │──►   ┌─────────────────────┐
                          └──────────────────────────────────────┘      │ VERCELL API (thin)   │
                              │                                       │ map + GeoJSON        │
                              │ historical spills (preloaded)         └──────────┬──────────┘
                              └────────────────────────────────────►             ▼
                                                                     ┌─────────────────────┐
                                                                     │ FRONTEND React+MapLibre│
                                                                     │ existing + live spills│
                                                                     │ vessel correlation card│
                                                                     └─────────────────────┘
```

## Vessel Correlation Output (per spill)

For each detected spill, the system reports:

```
Likely vessel:          Vessel A (MMSI)
Vessel type:            Tanker
Correlation score:      87%
Distance from spill:    2.4 km
Track intersection:     Yes
Vessel speed:           3.1 kn (near-0 = discharge signature)
Vessel direction:       ~due south, consistent with drift
Oil type:               Crude (heavy)          ← from histogram analysis
```

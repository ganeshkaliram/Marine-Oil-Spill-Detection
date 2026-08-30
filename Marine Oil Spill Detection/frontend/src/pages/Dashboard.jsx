import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

// Relative paths work in dev (Vite proxies /api -> localhost:8000) and on Vercel.
const API = import.meta.env.VITE_API_URL || "";
const VESSEL_REFRESH_MS = 3000;   // live vessel movement cadence
const DATA_REFRESH_MS = 15000;    // spills / attribution refresh

// MarineTraffic-style dark ocean basemap (raster from CARTO).
const OCEAN_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap © CARTO",
    },
  },
  layers: [
    { id: "ocean", type: "background", paint: { "background-color": "#0b1c34" } },
    { id: "carto", type: "raster", source: "carto" },
  ],
};

// Vessel icon colors by type (MarineTraffic-like).
const TYPE_COLOR = {
  tanker: "#ef4444",
  chemical: "#f97316",
  cargo: "#3b82f6",
  passenger: "#22c55e",
  other: "#94a3b8",
};

export default function Dashboard() {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const vesselMarkers = useRef({});
  const [slicks, setSlicks] = useState([]);
  const [historical, setHistorical] = useState([]);
  const [reports, setReports] = useState([]);
  const [vessels, setVessels] = useState([]);
  const [suspectMmsi, setSuspectMmsi] = useState(null);
  const [status, setStatus] = useState("Connecting…");

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: OCEAN_STYLE,
      center: [10.5, 10.5],
      zoom: 8,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    refreshData();
    const tData = setInterval(refreshData, DATA_REFRESH_MS);
    const tVessels = setInterval(refreshVessels, VESSEL_REFRESH_MS);
    return () => {
      clearInterval(tData);
      clearInterval(tVessels);
      map.remove();
    };
  }, []);

  async function refreshData() {
    try {
      const [s, h, r] = await Promise.all([
        fetch(`${API}/api/v1/detections/demo`).then((x) => x.json()),
        fetch(`${API}/api/v1/detections/historical`).then((x) => x.json()),
        fetch(`${API}/api/v1/attribution/demo`).then((x) => x.json()),
      ]);
      setSlicks(s);
      setHistorical(h);
      setReports(r);
      setSuspectMmsi(r[0]?.top_suspect?.mmsi ?? null);
      drawSpills(s, h, r);
      setStatus(`● LIVE · ${r.length} active spill · ${h.length} historical · ${new Date().toLocaleTimeString()}`);
    } catch (err) {
      setStatus(`⚠️ ${err.message} — start backend: uvicorn app.main:app`);
    }
  }

  async function refreshVessels() {
    try {
      const list = await fetch(`${API}/api/v1/ais/live`).then((x) => x.json());
      setVessels(list);
      updateVesselMarkers(list);
    } catch (e) {
      /* backend not reachable yet — skip */
    }
  }

  function updateVesselMarkers(list) {
    const map = mapRef.current;
    if (!map) return;
    const seen = new Set();
    list.forEach((v) => {
      seen.add(v.mmsi);
      let el = vesselMarkers.current[v.mmsi];
      if (!el) {
        el = makeVesselElement(v);
        vesselMarkers.current[v.mmsi] = el;
        el.marker = new maplibregl.Marker({ element: el, anchor: "center" })
          .setPopup(new maplibregl.Popup({ offset: 20 }).setHTML(popupHTML(v)))
          .addTo(map);
      }
      // Update position + rotation so vessels visibly move.
      el.querySelector(".boat").style.transform = `rotate(${v.cog_deg}deg)`;
      el._sog = v.sog_knots;
      el.marker.setLngLat([v.lon, v.lat]);
    });
    // Remove vessel markers that disappeared.
    Object.keys(vesselMarkers.current).forEach((mmsi) => {
      if (!seen.has(mmsi)) {
        vesselMarkers.current[mmsi].marker.remove();
        delete vesselMarkers.current[mmsi];
      }
    });
  }

  function drawSpills(slicks, historical, reports) {
    const map = mapRef.current;
    if (!map) return;
    if (map._spillLayer) {
      map._spillLayer.forEach((m) => m.remove());
      map._spillLayer = [];
    }
    map._spillLayer = [];

    historical.forEach((sp) => {
      const m = new maplibregl.Marker({ color: "#94a3b8", scale: 0.7 })
        .setLngLat([sp.centroid.lon, sp.centroid.lat])
        .setPopup(new maplibregl.Popup({ offset: 20 }).setHTML(
          `<b>${sp.status.toUpperCase()} spill</b><br/>${sp.oil_type}<br/>${fmtArea(sp.area_m2)}`));
      m.addTo(map);
      map._spillLayer.push(m);
    });

    reports.forEach((rep) => {
      const slick = slicks.find((s) => s.id === rep.slick_id);
      if (!rep.top_suspect) return;
      const lat = slick?.geometry.centroid_lat ?? 10.5;
      const lon = slick?.geometry.centroid_lon ?? 10.5;
      const t = rep.top_suspect;
      const el = document.createElement("div");
      el.className = "spill-pin";
      el.innerHTML = `<div class="pulse"></div><div class="core">⚠</div>`;
      const m = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lon, lat])
        .setPopup(new maplibregl.Popup({ offset: 20 }).setHTML(
          `<b>⚠ LIVE OIL SPILL</b><br/>Oil: ${slick?.oil_type ?? "n/a"}<br/>` +
          `<b>${t.vessel_name ?? `MMSI ${t.mmsi}`}</b><br/>` +
          `Correlation: ${(t.correlation_score * 100).toFixed(0)}% · ${t.distance_from_spill_km} km`));
      m.addTo(map);
      map._spillLayer.push(m);
    });
  }

  // ---- render ----
  return (
    <div className="layout">
      <aside className="panel">
        <div className="panel-head">
          <div className="title-row">
            <div className="logo-dot" />
            <div>
              <h1>OilSpill<span>Ops</span></h1>
              <div className="subtitle">Maritime Surveillance Console</div>
            </div>
          </div>
          <div className={`status ${status.includes("LIVE") ? "live" : ""}`}>{status}</div>
        </div>

        <div className="legend">
          <span><i className="lg lg-tanker" /> Tanker</span>
          <span><i className="lg lg-chemical" /> Chemical</span>
          <span><i className="lg lg-cargo" /> Cargo</span>
          <span><i className="lg lg-spill" /> Spill alert</span>
        </div>

        <h3 className="section-title">LIVE VESSELS — {vessels.length}</h3>
        <div className="vessel-list">
          {vessels.map((v) => (
            <div key={v.mmsi} className={`vessel-row ${v.mmsi === suspectMmsi ? "suspect" : ""}`}>
              <span className={`mini-boat ${v.vessel_type}`} />
              <div>
                <div className="v-name">{v.name} {v.mmsi === suspectMmsi && "🔎"}</div>
                <div className="v-meta">
                  {v.vessel_type} · {v.sog_knots} kn · {v.cog_deg}°
                </div>
              </div>
            </div>
          ))}
        </div>

        <h3 className="section-title">ATTRIBUTION</h3>
        {reports.length === 0 && (
          <p className="hint">Run <code>python scripts/generate_demo_data.py</code> then reload.</p>
        )}
        {reports.map((rep) => (
          <CorrelationCard key={rep.slick_id} rep={rep} slick={slicks.find((s) => s.id === rep.slick_id)} />
        ))}

        <h3 className="section-title">HISTORICAL SPILLS</h3>
        {historical.map((h) => (
          <div key={h.id} className="card hist">
            <span className="hist-dot" /> {h.oil_type}
            <span className="hist-meta">{fmtArea(h.area_m2)} · {new Date(h.detected_at).toLocaleDateString()}</span>
          </div>
        ))}
      </aside>
      <div ref={mapContainer} className="map" />
    </div>
  );
}

// ---- Marker element builders ----

function makeVesselElement(v) {
  const el = document.createElement("div");
  el.className = "vessel-marker";
  el.innerHTML = `
    <div class="boat ${v.vessel_type}" style="transform: rotate(${v.cog_deg}deg)">
      <svg viewBox="0 0 24 24" width="26" height="26">
        <path d="M12 2 L17 19 L12 15.5 L7 19 Z" fill="${TYPE_COLOR[v.vessel_type] || "#94a3b8"}" stroke="#fff" stroke-width="0.8"/>
      </svg>
    </div>
    <div class="vessel-label">${v.name}</div>`;
  return el;
}

function popupHTML(v) {
  const color = TYPE_COLOR[v.vessel_type] || "#94a3b8";
  return `<div style="font-family:sans-serif">
    <b>${v.name}</b><br/>
    <span style="color:${color}">${v.vessel_type}</span> · MMSI ${v.mmsi}<br/>
    SOG ${v.sog_knots} kn · COG ${v.cog_deg}°<br/>
    <span style="font-size:11px;color:#94a3b8">${v.lat}, ${v.lon}</span></div>`;
}

function CorrelationCard({ rep, slick }) {
  const t = rep.top_suspect;
  return (
    <div className={`card ${t ? "active" : ""}`}>
      <div className="card-title">
        ⚠ Live Spill <span className="hash">#{rep.slick_id.replace("slick_", "").slice(0, 6)}</span>
        {slick && <span className="oil-tag">{slick.oil_type}</span>}
      </div>
      {t ? (
        <div className="corr">
          <div className="corr-row"><span className="lbl">Likely vessel</span><b>{t.vessel_name ?? `MMSI ${t.mmsi}`}</b></div>
          <div className="corr-row"><span className="lbl">Vessel type</span><span>{t.vessel_class ?? "n/a"}</span></div>
          <div className="corr-row"><span className="lbl">Distance from spill</span><span>{t.distance_from_spill_km} km</span></div>
          <div className="corr-row"><span className="lbl">Track intersection</span><span>{t.track_intersection ? "Yes ✓" : "No"}</span></div>
          <div className="corr-row"><span className="lbl">Vessel speed</span><span>{t.vessel_speed_knots} kn {t.vessel_speed_knots < 2 ? "(discharge)" : ""}</span></div>
          <div className="meter"><span className="meter-fill" style={{ width: `${t.correlation_score * 100}%` }} /></div>
          <span className="pct">Correlation: {(t.correlation_score * 100).toFixed(0)}%</span>
        </div>
      ) : (
        <span>No suspect assigned (AIS window empty).</span>
      )}
    </div>
  );
}

function fmtArea(m2) {
  if (m2 >= 1e6) return `${(m2 / 1e6).toFixed(1)} km²`;
  return `${Math.round(m2)} m²`;
}

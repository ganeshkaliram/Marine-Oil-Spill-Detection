import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

// Relative paths work both in dev (Vite proxies /api -> localhost:8000) and on
// Vercel (serverless functions at `/api/...`). Override with VITE_API_URL if
// the API lives elsewhere.
const API = import.meta.env.VITE_API_URL || "";
const REFRESH_MS = 15000; // simulate "live" monitoring refresh

export default function Dashboard() {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [slicks, setSlicks] = useState([]);
  const [historical, setHistorical] = useState([]);
  const [reports, setReports] = useState([]);
  const [status, setStatus] = useState("Loading…");

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [10.5, 10.5],
      zoom: 4,
    });
    mapRef.current = map;
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => {
      clearInterval(timer);
      map.remove();
    };
  }, []);

  async function refresh() {
    try {
      const resp = await fetch(`${API}/api/health`);
      if (!resp.ok) throw new Error("backend not reachable");
      const [s, h, r] = await Promise.all([
        fetch(`${API}/api/v1/detections/demo`).then((x) => x.json()),
        fetch(`${API}/api/v1/detections/historical`).then((x) => x.json()),
        fetch(`${API}/api/v1/attribution/demo`).then((x) => x.json()),
      ]);
      setSlicks(s);
      setHistorical(h);
      setReports(r);
      const time = new Date().toLocaleTimeString();
      setStatus(`● LIVE — ${s.length} active · ${h.length} historical · ${time}`);
      redraw(s, h, r);
    } catch (err) {
      setStatus(`⚠️ ${err.message} — start backend: uvicorn app.main:app`);
    }
  }

  function redraw(slicks, historical, reports) {
    const map = mapRef.current;
    if (!map) return;
    // Clear previous markers
    if (map._dupMarkers) map._dupMarkers.forEach((m) => m.remove());
    map._dupMarkers = [];

    // Historical spills - grey markers
    historical.forEach((sp) => {
      const m = new maplibregl.Marker({ color: "#94a3b8" })
        .setLngLat([sp.centroid.lon, sp.centroid.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 25 }).setHTML(
            `<b>${sp.status.toUpperCase()} spill</b><br/>${sp.oil_type}<br/>${formatArea(sp.area_m2)}`
          )
        );
      m.addTo(map);
      map._dupMarkers.push(m);
    });

    // Report top suspect markers link to slick by id
    reports.forEach((rep) => {
      const slick = slicks.find((s) => s.id === rep.slick_id);
      if (!rep.top_suspect) return;
      const lat = slick?.geometry.centroid_lat ?? 10.5;
      const lon = slick?.geometry.centroid_lon ?? 10.5;
      const t = rep.top_suspect;
      const m = new maplibregl.Marker({ color: "#ef4444" })
        .setLngLat([lon, lat])
        .setPopup(
          new maplibregl.Popup({ offset: 25 }).setHTML(
            `<b>⚠ LIVE OIL SPILL</b><br/>Oil: ${slick?.oil_type ?? "n/a"}<br/>` +
              `<b>Likely vessel: ${t.vessel_name ?? "n/a"}</b><br/>` +
              `Correlation: ${(t.correlation_score * 100).toFixed(0)}%<br/>` +
              `Distance from spill: ${t.distance_from_spill_km} km`
          )
        );
      m.addTo(map);
      map._dupMarkers.push(m);
    });
  }

  return (
    <div className="layout">
      <aside className="panel">
        <div className="panel-head">
          <h2>Marine Oil Spill Monitor</h2>
          <div className={`status ${status.includes("LIVE") ? "live" : ""}`}>{status}</div>
        </div>

        <h3 className="section-title">🟢 Active Spills & Attribution</h3>
        {reports.length === 0 && (
          <p className="hint">
            Run <code>python scripts/generate_demo_data.py</code> then reload.
          </p>
        )}
        {reports.map((rep) => (
          <CorrelationCard key={rep.slick_id} rep={rep} slick={slicks.find((s) => s.id === rep.slick_id)} />
        ))}

        <h3 className="section-title">History (Existing Spills)</h3>
        {historical.map((h) => (
          <div key={h.id} className="card hist">
            <span className="hist-dot" /> {h.oil_type}
            <span className="hist-meta">
              {formatArea(h.area_m2)} · {new Date(h.detected_at).toLocaleDateString()}
            </span>
          </div>
        ))}
      </aside>
      <div ref={mapContainer} className="map" />
    </div>
  );
}

function CorrelationCard({ rep, slick }) {
  const t = rep.top_suspect;
  return (
    <div className={`card ${t ? "active" : ""}`}>
      <div className="card-title">
        ⚠ Live Spill {rep.slick_id.replace("slick_", "").slice(0, 6)}
        {slick && <span className="oil-tag">{slick.oil_type}</span>}
      </div>
      {t ? (
        <div className="corr">
          <div className="corr-row">
            <span className="lbl">Likely vessel</span>
            <b>{t.vessel_name ?? `MMSI ${t.mmsi}`}</b>
          </div>
          <div className="corr-row">
            <span className="lbl">Vessel type</span>
            <span>{t.vessel_class ?? "n/a"}</span>
          </div>
          <div className="corr-row">
            <span className="lbl">Distance from spill</span>
            <span>{t.distance_from_spill_km} km</span>
          </div>
          <div className="corr-row">
            <span className="lbl">Track intersection</span>
            <span>{t.track_intersection ? "Yes ✓" : "No"}</span>
          </div>
          <div className="corr-row">
            <span className="lbl">Vessel speed</span>
            <span>{t.vessel_speed_knots} kn {t.vessel_speed_knots < 2 ? "(discharge signature)" : ""}</span>
          </div>
          <div className="meter">
            <span className="meter-fill" style={{ width: `${t.correlation_score * 100}%` }} />
          </div>
          <span className="pct">Correlation: {(t.correlation_score * 100).toFixed(0)}%</span>
        </div>
      ) : (
        <span>No suspect assigned (AIS window empty).</span>
      )}
    </div>
  );
}

function formatArea(m2) {
  if (m2 >= 1e6) return `${(m2 / 1e6).toFixed(1)} km²`;
  return `${Math.round(m2)} m²`;
}

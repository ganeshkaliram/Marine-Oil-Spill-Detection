import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

const API = "http://localhost:8000";
const DEMO_REPORTS_URL = `${API}/api/v1/attribution/demo`;

export default function Dashboard() {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [slicks, setSlicks] = useState([]);
  const [reports, setReports] = useState([]);
  const [status, setStatus] = useState("Loading…");

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [10.5, 10.5],
      zoom: 5,
    });
    mapRef.current = map;
    fetchDemoData();
    return () => map.remove();
  }, []);

  async function fetchDemoData() {
    try {
      const resp = await fetch(`${API}/health`);
      if (!resp.ok) throw new Error("backend not reachable");
      const [s, r] = await Promise.all([
        fetch(`${API}/api/v1/detections/demo`).then((x) => x.json()),
        fetch(DEMO_REPORTS_URL).then((x) => x.json()),
      ]);
      setSlicks(s);
      setReports(r);
      setStatus(`⚙️ Ready — ${s.length} detections, ${r.length} reports`);
      drawPoints(s, r);
    } catch (err) {
      setStatus(`⚠️ ${err.message} — start backend: uvicorn app.main:app`);
    }
  }

  function drawPoints(slicks, reports) {
    const map = mapRef.current;
    if (!map) return;
    map.on("load", () => {
      slicks.forEach((sl, i) => {
        new maplibregl.Marker({ color: "#e11d48" })
          .setLngLat([sl.geometry.centroid_lon, sl.geometry.centroid_lat])
          .setPopup(new maplibregl.Popup({ offset: 25 }).setHTML(
            `<b>Slick ${sl.id}</b><br/>Conf: ${sl.confidence}<br/>Age: ${sl.estimated_age_hours}h`
          ))
          .addTo(map);
      });
      reports.forEach((rep) => {
        const top = rep.top_suspect;
        if (!top) return;
        new maplibregl.Marker({ color: "#3b82f6" })
          .setLngLat([rep.slick_lon ?? 10.5, rep.slick_lat ?? 10.5])
          .setPopup(new maplibregl.Popup({ offset: 25 }).setHTML(
            `<b>Suspect MMSI ${top.mmsi}</b><br/>Confidence: ${top.overall_confidence}`
          ))
          .addTo(map);
      });
    });
  }

  return (
    <div className="layout">
      <aside className="panel">
        <h2>Detections</h2>
        <div className="status">{status}</div>
        {reports.length === 0 && (
          <p className="hint">
            Run <code>python scripts/generate_demo_data.py</code> then reload.
          </p>
        )}
        {reports.map((rep) => (
          <div key={rep.slick_id} className="card">
            <strong>Slick {rep.slick_id}</strong>
            {rep.top_suspect ? (
              <div>
                <span>Top suspect: MMSI {rep.top_suspect.mmsi}</span>
                <div className="meter">
                  <span
                    className="meter-fill"
                    style={{ width: `${rep.top_suspect.overall_confidence * 100}%` }}
                  />
                </div>
                <span className="pct">
                  {(rep.top_suspect.overall_confidence * 100).toFixed(0)}% confidence
                </span>
              </div>
            ) : (
              <span>No suspect assigned</span>
            )}
          </div>
        ))}
      </aside>
      <div ref={mapContainer} className="map" />
    </div>
  );
}

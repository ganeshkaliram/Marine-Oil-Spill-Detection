// Vercel serverless endpoint: /api/v1/ais/live
// Self-contained JS vessel simulator so the deployed site shows moving vessels
// even without the Python backend. Includes trader-critical fields:
// destination, ETA, cargo type, trust score.

const WAYPOINTS = [
  { mmsi: 413000111, name: "MT SUSPECT-ONE", type: "tanker", wps: [[12.8,43.2],[12.5,43.5],[12.0,44.0],[10.5,43.0]], kn: 12, dest: "SGSIN", cargo: "crude-oil", len: 183, brd: 32 },
  { mmsi: 636000222, name: "MV INNOCENT", type: "cargo", wps: [[9.5,10.8],[10.0,10.5],[10.5,11.0],[11.5,12.0]], kn: 15, dest: "AEJEA", cargo: "general-cargo", len: 225, brd: 32 },
  { mmsi: 538009330, name: "MT ALPHA CRUDE", type: "tanker", wps: [[11.0,12.5],[10.5,11.8],[9.8,11.0],[9.2,10.5]], kn: 12, dest: "CNQGD", cargo: "lng", len: 274, brd: 45 },
  { mmsi: 477003410, name: "MT BETA CHEM", type: "chemical", wps: [[10.2,9.5],[10.8,10.0],[11.5,10.8],[12.0,11.5]], kn: 14, dest: "JEDDAH", cargo: "chemical", len: 180, brd: 28 },
  { mmsi: 241002200, name: "MT GAMMA FUEL", type: "tanker", wps: [[9.5,11.5],[10.0,11.0],[10.5,10.5],[11.0,9.5]], kn: 11, dest: "DJJIB", cargo: "fuel-oil", len: 140, brd: 22 },
  { mmsi: 255803550, name: "MT DELTA LNG", type: "tanker", wps: [[12.0,10.0],[11.5,10.5],[10.8,11.0],[10.0,11.5]], kn: 14, dest: "SAJED", cargo: "lng", len: 300, brd: 48 },
  { mmsi: 219004414, name: "MV EPSILON C", type: "cargo", wps: [[10.5,9.0],[10.8,9.8],[11.2,10.5],[11.0,11.2]], kn: 13, dest: "OMSLL", cargo: "containers", len: 190, brd: 30 },
  { mmsi: 352003720, name: "MT ZETA PETRO", type: "chemical", wps: [[11.5,12.0],[11.0,11.5],[10.5,11.0],[9.8,10.2]], kn: 9, dest: "EGPSD", cargo: "chemical", len: 160, brd: 25 },
];

module.exports = (req, res) => {
  const now = Date.now() / 1000;
  const cycle = 600; // 10 minute route cycle
  const out = WAYPOINTS.map((v) => {
    const t = (now % cycle) / cycle; // 0..1 progress through route
    const totalWps = v.wps.length;
    const segFloat = t * (totalWps - 1);
    const segIdx = Math.min(Math.floor(segFloat), totalWps - 2);
    const segT = segFloat - segIdx;

    // Interpolate position between waypoints
    const lat = v.wps[segIdx][0] + (v.wps[segIdx + 1][0] - v.wps[segIdx][0]) * segT;
    const lon = v.wps[segIdx][1] + (v.wps[segIdx + 1][1] - v.wps[segIdx][1]) * segT;

    // Add noise
    const nLat = lat + (Math.random() - 0.5) * 0.001;
    const nLon = lon + (Math.random() - 0.5) * 0.001;

    // Calculate bearing
    const dLat = v.wps[segIdx + 1][0] - v.wps[segIdx][0];
    const dLon = v.wps[segIdx + 1][1] - v.wps[segIdx][1];
    const cog = ((Math.atan2(dLon, dLat) * 180 / Math.PI) + 360) % 360;

    // ETA: simulate arrival in ~2-6 hours
    const hoursFromNow = 2 + (v.mmsi % 5);
    const eta = new Date(Date.now() + hoursFromNow * 3600000).toISOString();

    return {
      mmsi: v.mmsi,
      name: v.name,
      vessel_type: v.type,
      lat: Math.round(nLat * 1e5) / 1e5,
      lon: Math.round(nLon * 1e5) / 1e5,
      sog_knots: v.kn,
      cog_deg: Math.round(cog),
      destination: v.dest,
      cargo_type: v.cargo,
      eta: eta,
      ship_length_m: v.len,
      ship_breadth_m: v.brd,
      trust_score: v.mmsi === 413000111 ? 0.89 : 1.0,
      updated_at: new Date().toISOString(),
    };
  });
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json(out);
};

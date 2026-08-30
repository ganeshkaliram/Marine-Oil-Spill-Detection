// Vercel serverless endpoint: /api/v1/ais/live
// Self-contained JS vessel simulator so the deployed site shows moving vessels
// even without the Python backend. Positions advance with server time.
const FLEET = [
  { mmsi: 413000111, name: "MT SUSPECT-ONE", type: "tanker", lat: 10.48, lon: 10.46, kn: 1.2, cog: 165 },
  { mmsi: 636000222, name: "MV INNOCENT", type: "cargo", lat: 11.0, lon: 10.2, kn: 16.0, cog: 90 },
  { mmsi: 538009330, name: "MT ALPHA CRUDE", type: "tanker", lat: 9.9, lon: 10.8, kn: 12.0, cog: 220 },
  { mmsi: 477003410, name: "MT BETA CHEM", type: "chemical", lat: 10.7, lon: 10.1, kn: 14.0, cog: 45 },
  { mmsi: 241002200, name: "MT GAMMA FUEL", type: "tanker", lat: 10.3, lon: 11.0, kn: 10.5, cog: 300 },
  { mmsi: 255803550, name: "MT DELTA LNG", type: "tanker", lat: 11.2, lon: 10.9, kn: 11.0, cog: 180 },
  { mmsi: 219004414, name: "MV EPSILON C", type: "cargo", lat: 9.8, lon: 9.9, kn: 13.5, cog: 75 },
  { mmsi: 352003720, name: "MT ZETA PETRO", type: "chemical", lat: 10.6, lon: 10.4, kn: 9.0, cog: 250 },
];

module.exports = (req, res) => {
  const now = Date.now() / 1000;
  const out = FLEET.map((v) => {
    const km = v.kn * (now % 600) * 0.000514444; // loop every 10 min
    const dLat = (km * Math.cos((v.cog * Math.PI) / 180)) / 111.0;
    const dLon =
      (km * Math.sin((v.cog * Math.PI) / 180)) /
      (111.0 * Math.cos((v.lat * Math.PI) / 180));
    const wrap = (min, max, x) => min + ((((x - min) % (max - min)) + (max - min)) % (max - min));
    return {
      mmsi: v.mmsi,
      name: v.name,
      vessel_type: v.type,
      lat: Math.round(wrap(8, 13, v.lat + dLat) * 1e5) / 1e5,
      lon: Math.round(wrap(8, 13, v.lon + dLon) * 1e5) / 1e5,
      sog_knots: v.kn,
      cog_deg: v.cog,
      updated_at: new Date().toISOString(),
    };
  });
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json(out);
};

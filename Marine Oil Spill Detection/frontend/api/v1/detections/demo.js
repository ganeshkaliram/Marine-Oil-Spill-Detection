// Vercel serverless endpoint: /api/v1/detections/demo
// Serves a committed snapshot of generated demo detections so the deployed
// site is fully functional without the Python backend.
const detections = require("../../data/detections.json");

module.exports = (req, res) => {
  res.status(200).json(detections);
};

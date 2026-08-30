// Vercel serverless endpoint: /api/v1/detections/historical
const historical = require("../../data/historical.json");

module.exports = (req, res) => {
  res.status(200).json(historical);
};

// Vercel serverless endpoint: /api/v1/attribution/demo
const reports = require("../../data/reports.json");

module.exports = (req, res) => {
  res.status(200).json(reports);
};

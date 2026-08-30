module.exports = (req, res) => {
  res.status(200).json({ status: "ok", deploy: "vercel", version: "0.2.0" });
};

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend FastAPI server runs on :8000 in dev. Proxy /api and /health there
// so the frontend can call it without CORS issues.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});

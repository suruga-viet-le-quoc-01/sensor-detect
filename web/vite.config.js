import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // Dev-time only: proxies the Giám sát tab's API calls to uvicorn (src/web_api/main.py)
    // without needing CORS headers on the Python backend. Production serves the built SPA and
    // the API under the same origin via a reverse proxy instead.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "node",
  },
});

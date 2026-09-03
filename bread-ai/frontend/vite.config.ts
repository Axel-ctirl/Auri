/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * In development the UI runs here on :5173 and proxies /api to the FastAPI
 * server on :8000, so the browser sees one origin and cookies/CORS stay simple.
 * In production `npm run build` emits to dist/, which the backend serves.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Bind to localhost only. Bread is local-first; exposing the dev server on
    // the network is a deliberate act, not a default.
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
      "/openapi.json": "http://127.0.0.1:8000",
      "/docs": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});

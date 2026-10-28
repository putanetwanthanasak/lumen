import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Loopback only, never 0.0.0.0 (L60: no end-user auth, X-Demo-User is demo-only).
// The backend routes have no /api prefix, so the proxy strips it, as the one-server
// demo's mount does (L73). `--mode mock` answers from src/mock/server.ts instead of
// the API (src/api.ts); every other mode, the build included, calls the API.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  define: { __KIDNEE_MOCK__: JSON.stringify(mode === "mock") },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
}));

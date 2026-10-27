import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Loopback only, never 0.0.0.0 (L60: no end-user auth, X-Demo-User is demo-only).
// The backend routes have no /api prefix, so the proxy strips it. To be confirmed
// when the screens are wired to the real API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";
const enableHmr = process.env.VITE_ENABLE_HMR === "1";
const hmrHost = process.env.VITE_DEV_HMR_HOST ?? "127.0.0.1";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    hmr: enableHmr ? { host: hmrHost } : false,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});

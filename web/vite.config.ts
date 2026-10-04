import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  return {
    base: env.VITE_BASE || "/",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5177,
      strictPort: true,
      fs: {
        allow: [root, path.resolve(root, "../../gridiron/web")],
      },
      proxy: {
        "/tpe-api": {
          target: process.env.VITE_TPE_API_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/tpe-api/, ""),
        },
      },
    },
  };
});

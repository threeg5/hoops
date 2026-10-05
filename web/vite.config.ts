import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));

function writeHtaccess(base: string) {
  const folder = base.endsWith("/") ? base : `${base}/`;
  if (folder === "/") return null;
  const body = `DirectoryIndex index.html
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase ${folder}
  RewriteRule ^index\\.html$ - [L]
  RewriteCond %{REQUEST_FILENAME} !-f
  RewriteCond %{REQUEST_FILENAME} !-d
  RewriteRule . ${folder}index.html [L]
</IfModule>
`;
  return {
    name: "write-htaccess",
    apply: "build" as const,
    closeBundle() {
      fs.writeFileSync(path.join(root, "dist", ".htaccess"), body);
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  const base = env.VITE_BASE || "/";
  return {
    base,
    plugins: [react(), writeHtaccess(base)].filter(Boolean),
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

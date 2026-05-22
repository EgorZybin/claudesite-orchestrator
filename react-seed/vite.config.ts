import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Two-pass build:
 *   vite build              → dist/client/  (with .vite/manifest.json + index.html)
 *   vite build --ssr ...    → dist/server/  (entry-server.js)
 * The renderer service consumes both: server bundle for renderToString,
 * client manifest for resolving hashed CSS/JS asset URLs.
 */
export default defineConfig(({ isSsrBuild }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: isSsrBuild ? "dist/server" : "dist/client",
    emptyOutDir: false, // client + server coexist; clean is done by react_builder
    ssrManifest: !isSsrBuild,
    manifest: !isSsrBuild,
  },
  ssr: {
    // Bundle these into the server output so the renderer service doesn't
    // resolve them from node_modules per-site at SSR time.
    noExternal: [
      "@radix-ui/react-accordion",
      "@radix-ui/react-slot",
      "class-variance-authority",
      "clsx",
      "lucide-react",
      "tailwind-merge",
      "tailwindcss-animate",
      "marked",
    ],
  },
}));

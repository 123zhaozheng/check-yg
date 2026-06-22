import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import { Features } from "lightningcss"
import path from "node:path"

// Chrome 108 (2022-11) has no oklch()/lab()/color-mix() support (all landed in
// 111). Lightning CSS transpiles them down to rgb()/computed fallbacks for both
// dev and build so the monochrome theme survives on legacy Chrome.
// targets version encoding: (major << 16) | (minor << 8) | patch
const cssTargets = { chrome: 108 << 16 }

// Force lab()/oklab() to also transpile to rgb — Lightning's chrome108
// downgrade path otherwise emits lab(), which Chrome 108 still cannot parse.
const cssInclude = Features.LabColors | Features.OklabColors

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  css: {
    lightningcss: {
      targets: cssTargets,
      include: cssInclude,
    },
  },
  build: {
    target: "chrome108",
    cssMinify: "lightningcss",
    outDir: "dist",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
})

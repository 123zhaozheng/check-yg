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
    // Windows 下 vite 默认把 'localhost' 解析成 IPv6 (::1)，浏览器走 IPv4
    // 127.0.0.1 时连接被拒。host: true 让其监听 0.0.0.0，IPv4/IPv6/局域网全通。
    host: true,
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

import { reactRouter } from "@react-router/dev/vite"
import tailwindcss from "@tailwindcss/vite"
import { Features } from "lightningcss"
import { defineConfig } from "vite"

// Chrome 108 (2022-11) has no oklch()/lab()/color-mix() support (all landed in
// 111). Lightning CSS transpiles them down to rgb()/computed fallbacks for both
// dev and build so the dark flagship theme survives on legacy Chrome.
// targets version encoding: (major << 16) | (minor << 8) | patch
const cssTargets = { chrome: 108 << 16 }

// Force lab()/oklab() to also transpile to rgb — Lightning's chrome108
// downgrade path otherwise emits lab(), which Chrome 108 still cannot parse.
const cssInclude = Features.LabColors | Features.OklabColors

export default defineConfig({
  resolve: { tsconfigPaths: true },
  plugins: [tailwindcss(), reactRouter()],
  css: {
    lightningcss: {
      targets: cssTargets,
      include: cssInclude,
    },
  },
  build: {
    target: "chrome108",
    cssMinify: "lightningcss",
  },
})

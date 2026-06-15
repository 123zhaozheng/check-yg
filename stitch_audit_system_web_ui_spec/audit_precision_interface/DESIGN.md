---
name: Audit Precision Interface
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#3a3939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353535'
  on-surface: '#e5e2e1'
  on-surface-variant: '#c4c7c9'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#8e9193'
  outline-variant: '#444749'
  surface-tint: '#c4c7c9'
  primary: '#ffffff'
  on-primary: '#2d3133'
  primary-container: '#e0e3e5'
  on-primary-container: '#626567'
  inverse-primary: '#5c5f61'
  secondary: '#bec6e0'
  on-secondary: '#283044'
  secondary-container: '#3f465c'
  on-secondary-container: '#adb4ce'
  tertiary: '#ffffff'
  on-tertiary: '#32302a'
  tertiary-container: '#e7e2d9'
  on-tertiary-container: '#67645d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e0e3e5'
  primary-fixed-dim: '#c4c7c9'
  on-primary-fixed: '#191c1e'
  on-primary-fixed-variant: '#444749'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#e7e2d9'
  tertiary-fixed-dim: '#cbc6bd'
  on-tertiary-fixed: '#1d1b16'
  on-tertiary-fixed-variant: '#494640'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353535'
  background-light: '#FFFFFF'
  foreground-light: '#020817'
  muted-light: '#F1F5F9'
  border-light: '#E2E8F0'
  background-dark: '#0A0A0A'
  foreground-dark: '#F8FAFC'
  muted-dark: '#1E293B'
  border-dark: '#334155'
  accent-positive: '#10B981'
  accent-negative: '#EF4444'
  accent-warning: '#F59E0B'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  mono-sm:
    fontFamily: jetbrainsMono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 8px
  container-max: 1440px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style
The design system is engineered for **Check-YG Web**, a high-stakes financial audit platform where accuracy, transparency, and trust are paramount. The target audience—financial auditors and corporate administrators—requires a workspace that minimizes cognitive load while maximizing data density.

The visual style is **Corporate / Modern**, strictly adhering to a professional and restrained aesthetic influenced by `shadcn/ui`. It leverages a high-fidelity utilitarian approach: clean layouts, subtle borders, and a focus on content over decoration. The emotional response should be one of focused productivity, reliability, and institutional security. Every element is purposeful, avoiding unnecessary flourishes to ensure the "audit trail" is always the primary focus.

## Colors
The palette is rooted in a sophisticated monochromatic scale, using deep navies and crisp slates to establish a "command center" atmosphere. While the system supports both modes, the **dark mode** is the flagship experience for prolonged analytical work, reducing eye strain.

- **Primary:** Used for high-emphasis actions and active states. In dark mode, this is a near-white slate; in light mode, a deep ink blue.
- **Muted:** Applied to secondary backgrounds, table headers, and decorative elements to create subtle layering without high-contrast interference.
- **Borders:** Crucial for the "restrained" look. Borders use low-contrast values to define structure without fragmenting the layout.
- **Semantic Colors:** Emerald for audits passed, Rose for discrepancies, and Amber for pending reviews. These should be used sparingly as small pips or subtle text highlights.

## Typography
The system utilizes **Inter** for all UI elements to ensure maximum legibility and a neutral, systematic tone. 

- **Weights:** Use `600` (SemiBold) for all headings to provide clear structural hierarchy. Body copy uses `400` (Regular), while functional labels (buttons, tabs, table headers) use `500` (Medium).
- **Tabular Data:** For financial figures, transaction IDs, and timestamps, use a monospaced font like **JetBrains Mono** to ensure numerical alignment in audit tables.
- **Hierarchy:** Maintain a tight scale. Mobile views should cap headlines at `headline-md` to preserve screen real estate for data tables.

## Layout & Spacing
This design system follows a **12-column Fixed Grid** for desktop views, centering content within a 1440px container to maintain readability on ultra-wide monitors. 

- **Rhythm:** An 8px base unit (Tailwind-aligned) governs all padding and margins. 
- **Density:** The dashboard layout uses high-density spacing (padding: 12px or 16px) to allow more information to be visible without scrolling. 
- **Adaptivity:** 
  - **Desktop:** Sidebar navigation (240px) + Fluid content area.
  - **Tablet:** Sidebar collapses to an icon-only rail or drawer; margins reduce to 24px.
  - **Mobile:** Single column layout; margins reduce to 16px; horizontal scrolling enabled for data tables.

## Elevation & Depth
Depth is conveyed through **Tonal Layers** rather than aggressive shadows, mimicking the `shadcn/ui` philosophy.

- **Background:** The base layer (`background`).
- **Surface:** Cards and main content areas sit on the base layer with a `1px` border of `border-muted`.
- **Shadows:** Use `shadow-sm` (subtle) for cards and `shadow-md` for floating elements like dropdown menus or popovers. Shadows should be neutral, using a low-opacity black (e.g., `rgba(0,0,0,0.1)`).
- **Interactive States:** Hovering over an interactive card or row should slightly lighten the background color rather than increasing shadow depth, maintaining a "flat" professional feel.

## Shapes
The shape language is precise and conservative, utilizing small radii to maintain a serious, "software-tool" aesthetic.

- **Inputs & Buttons:** 6px radius (`rounded-md`) for a sharp, modern feel.
- **Cards & Containers:** 8px radius (`rounded-lg`) to provide a clear but soft distinction from the background.
- **Dialogs & Modals:** 12px radius (`rounded-xl`) to signal a break in the primary workflow and focus attention on the overlay.

## Components
Consistent component styling ensures the audit interface feels like a singular, integrated tool.

- **Buttons:** 
  - **Primary:** Solid background (`primary`), white or near-white text. 
  - **Secondary:** Outline with `border` color and transparent background.
  - **Size:** Standard height 36px-40px.
- **Input Fields:** 1px border, 6px radius. Focus state uses a `2px` ring of the primary color with an offset.
- **Data Tables:** The core of the system. Use `body-sm` for rows, `label-sm` with `muted` foreground for headers. Row hover state: `muted` background.
- **Icons:** Use `lucide-react`. 
  - `size-4` (16px) for inline text and buttons.
  - `size-5` (20px) for topbar navigation and sidebar icons.
  - `size-6` (24px) for empty states or large dashboard cards.
- **Charts:** Follow the reference dark aesthetic. Use thin line weights (1.5px or 2px) and subtle area gradients. Use the semantic accent colors (positive/negative) for data series.
- **Chips/Badges:** Small, `label-sm` text, 2px radius or pill-shaped, using low-saturation versions of semantic colors for status (e.g., "Verified", "Flagged").
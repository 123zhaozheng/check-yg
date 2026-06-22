---
name: Monochrome Precision
colors:
  surface: '#faf9f9'
  surface-dim: '#dbdad9'
  surface-bright: '#faf9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f3'
  surface-container: '#efeded'
  surface-container-high: '#e9e8e8'
  surface-container-highest: '#e3e2e2'
  on-surface: '#1b1c1c'
  on-surface-variant: '#4c4546'
  inverse-surface: '#2f3031'
  inverse-on-surface: '#f2f0f0'
  outline: '#7e7576'
  outline-variant: '#cfc4c5'
  surface-tint: '#5e5e5e'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1b1b1b'
  on-primary-container: '#848484'
  inverse-primary: '#c6c6c6'
  secondary: '#5e5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e1dfdf'
  on-secondary-container: '#636262'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#1b1b1b'
  on-tertiary-container: '#848484'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c6'
  on-primary-fixed: '#1b1b1b'
  on-primary-fixed-variant: '#474747'
  secondary-fixed: '#e4e2e2'
  secondary-fixed-dim: '#c7c6c6'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#464747'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c6'
  on-tertiary-fixed: '#1b1b1b'
  on-tertiary-fixed-variant: '#474747'
  background: '#faf9f9'
  on-background: '#1b1c1c'
  surface-variant: '#e3e2e2'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  title-sm:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Hanken Grotesk
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-caps:
    fontFamily: Hanken Grotesk
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
  max-width: 1440px
---

## Brand & Style
The design system for this financial audit platform is built on a foundation of absolute precision, neutrality, and structural clarity. It adopts a **High-Contrast Monochrome** style that eschews color in favor of a sophisticated luminance scale. By removing the emotional weight of hue, the UI directs the auditor's focus entirely toward data integrity and transactional patterns.

The brand personality is authoritative yet unobtrusive. It mimics the aesthetic of high-end editorial publishing and archival documents, utilizing whitespace and rigorous grid alignment to create a sense of trust and stability. The emotional response should be one of "calm focus"—reducing cognitive load during complex data analysis through a disciplined, predictable visual language.

## Colors
Hierarchy is established strictly through a 9-level luminance scale. 
- **Core Action:** Pure Black (`#000000`) is reserved for primary actions, heavy headers, and active states.
- **Surface Strategy:** The "Canvas Base" (`#f7f7f8`) provides a soft off-white foundation that reduces eye strain compared to pure white, which is saved for elevated "Surface" cards.
- **Semantic Neutrality:** In the absence of red or green, "Error" or "Alert" states are indicated by bolding, high-contrast black backgrounds, or heavy 2px black borders. Success and progress are visualized through grayscale density—moving from Light Gray to Solid Black as tasks reach completion.

## Typography
The system employs a dual-font strategy:
1.  **Hanken Grotesk:** A contemporary, sharp sans-serif used for all UI labels, headers, and prose. It provides a technical but approachable feel.
2.  **JetBrains Mono:** Utilized exclusively for financial figures, transaction IDs, and timestamps. The monospaced nature ensures that decimals and digits align vertically in tables, which is critical for rapid audit scanning.

**Formatting Rules:**
- Large display titles use tight letter spacing.
- Small labels and captions use increased letter spacing and uppercase styling to maintain legibility despite their small scale.
- Financial amounts should never use "bold" unless they represent a total or a final result.

## Layout & Spacing
This design system utilizes a **Fixed Grid** model for the main dashboard content to ensure data density remains manageable. 

- **Grid:** A 12-column system on desktop with a fixed 24px gutter.
- **Rhythm:** All vertical spacing follows a 4px baseline, with standard increments of 8px, 16px, 24px, 32px, 48px, and 64px.
- **Alignment:** Financial tables should be flush with the margins. The sidebar navigation is fixed at 240px, while the main content area occupies the remaining span up to the 1440px max-width. 
- **Reflow:** On mobile, the grid switches to a 4-column layout with 16px margins, and all table data should transition to a card-based list view to maintain readability of monospaced figures.

## Elevation & Depth
Depth is created through **Tonal Layering** and architectural "fine lines" rather than dramatic shadows.

- **Level 0 (Canvas):** The base background (`#f7f7f8`).
- **Level 1 (Cards/Surfaces):** Pure White (`#ffffff`) surfaces with a 1px border of `#e5e5e5`. A subtle shadow (`0 1px 2px rgba(0,0,0,0.04)`) is used to separate cards from the canvas.
- **Separation:** 1px solid lines in `#bfbfbf` or `#e5e5e5` are used to define structural boundaries within a surface (e.g., table headers, form sections).
- **Interactivity:** Elements do not "lift" on hover; instead, they change their border-weight from 1px to 2px or shift their background color to `#f0f0f0` to indicate tactility.

## Shapes
The shape language is "Soft" yet disciplined. A standard corner radius of `4px` (`0.25rem`) is applied to buttons, input fields, and small containers to prevent the UI from feeling overly aggressive or "brutalist."

- **Cards:** Use `rounded-lg` (`8px`) to define major content areas.
- **Status Capsules:** These are the only exception to the rule, utilizing a full pill-shape (circular ends) to distinguish them as metadata/status indicators separate from interactive buttons.
- **Active Indicators:** Navigation highlights use a `3px` wide vertical bar with sharp corners to signify the "active" path.

## Components
- **Buttons:**
    - **Primary:** Solid `#000000` background with `#ffffff` text. No shadow.
    - **Secondary:** 1px `#000000` border, transparent background, `#000000` text.
    - **Tertiary:** Text-only, underlined on hover.
- **Form Fields:** Use a minimalist "fine-border" style (bottom border only, 1px `#bfbfbf`) that thickens to 2px `#000000` on focus. Placeholders are set in `#8c8c8c`.
- **Status Capsules:** Grayscale pill system.
    - *Initial (Importing):* `#f0f0f0` bg, `#595959` text.
    - *In-Progress (Cleaning):* `#bfbfbf` bg, `#ffffff` text.
    - *Final (Reported):* `#000000` bg, `#ffffff` text.
- **Data Tables:** 
    - Header background is `#f7f7f8`. 
    - 1px horizontal dividers in `#e5e5e5`. 
    - No zebra striping. 
    - On hover, a row's background shifts to `#f0f0f0`.
- **Active Navigation:** Active sidebar items are marked by a 3px black vertical line on the left edge and a font-weight shift to Bold.
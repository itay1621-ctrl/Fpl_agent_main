# FPL Strategy Engine — Design System & Visual Specification

## Design Philosophy: Modern Football Analytics Terminal

The design language reflects the authority of elite Premier League data analytics — clean, disciplined, information-dense, and highly legible. It discards generic "AI SaaS" tropes (purple-to-cyan mesh gradients, glowing shadows, emoji icons, stacked nested cards) in favor of crisp editorial structure, tabular precision, and cohesive sports typography.

## Color Palette & Semantic Tokens

### Brand Foundations
- **Premier League Purple (Primary Brand)**:
  - Deep Heritage Purple: `#37003c` (Used for header surfaces, brand bars, accent anchors)
  - Night Purple (Dark Mode Ground): `#1a001d` / `#130015`
  - Subtle Tint: `#4b0852`
- **Pitch Green (Action & Accent)**:
  - Electric Stadium Green: `#01fc7a` (Primary action, key metric highlights)
  - Dark Accent Green: `#008744` (Pitch turf primary)
  - Deep Turf Green: `#083a21` (Bench turf secondary)
- **Neutral Grounds & Surfaces**:
  - Light Ground: `#f8fafc` (Slate 50)
  - Light Card Surface: `#ffffff`
  - Light Border: `#e2e8f0` (Slate 200)
  - Light Subdued Text: `#64748b` (Slate 500)
  - Light Heading Text: `#0f172a` (Slate 900)
  - Dark Ground: `#090d16` (Deep Slate / Night)
  - Dark Card Surface: `#131b2e`
  - Dark Border: `#1e293b` (Slate 800)
  - Dark Subdued Text: `#94a3b8` (Slate 400)
  - Dark Heading Text: `#f8fafc` (Slate 50)

### Status & Difficulty Semantics (FDR Standards)
- **FDR 1 (Very Easy)**: Emerald `#059669` / `#10b981`
- **FDR 2 (Easy)**: Green `#16a34a` / `#22c55e`
- **FDR 3 (Moderate)**: Neutral Slate `#64748b` / Amber `#d97706`
- **FDR 4 (Difficult)**: Rose `#e11d48` / `#f43f5e`
- **FDR 5 (Very Difficult)**: Dark Crimson `#9f1239` / `#be123c`
- **Urgent / Error / Danger**: Rose `#e11d48` (Clean indicator, never neon halo)

## Typography

- **Font Family**: Modern system UI sans-serif stack with high legibility:
  `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **Tabular Numerals**: Every statistical column, cost, bank, countdown, score, and rank uses `tabular-nums` (`font-variant-numeric: tabular-nums`) to prevent layout jitter and align figures cleanly.
- **Hierarchy & Scale**:
  - Page Titles: `text-2xl font-bold tracking-tight` (Never `font-black` 900 shouting)
  - Section Headings: `text-lg sm:text-xl font-bold text-slate-900 dark:text-slate-100`
  - Card Labels / Metrics: `text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400`
  - Metric Figures: `text-xl sm:text-2xl font-bold tracking-tight tabular-nums`
  - Body & Explanations: `text-sm leading-relaxed text-slate-600 dark:text-slate-300`
  - Microcopy & Badges: `text-[11px] font-semibold tabular-nums`

## Component Standards

### Cards & Surfaces
- Avoid nested cards of identical border and radius. A container has at most one elevation level.
- Border radius: consistent `rounded-xl` (12px) or `rounded-lg` (8px). Never inconsistent 2xl mixed with sharp corners.
- Borders: Crisp 1px borders (`border border-slate-200 dark:border-slate-800`). No `border-l-4` side-tabs, no clashing top-border strips.
- Shadows: Subtle, soft elevation (`shadow-sm` or `shadow-md` with soft blur). No hard offset neobrutalist black blocks, no glowing neon rings.

### Icons
- Replace raw Unicode emojis (`📋`, `🗓️`, `📊`, `📡`, `💰`, `🏆`, `⏱️`, `💡`, `⚡`, `👀`, `🔒`) with clean, consistent 16-20px SVG outline icons.
- Stroke width: uniform 1.75px or 2px.

### Navigation & Tabs
- Desktop Tab Bar: Clean pill or underline tab indicator using Premier League Purple / Pitch Green, with subtle hover state. Never error-red underline.
- Mobile Bottom Navigation: Fixed bottom bar, clean icon + 10px label layout with proper tap target (48x48px min touch target), clear active indicator, and no horizontal clipping.

### Modals & Dialogs
- Backdrops: Crisp dark backdrop `bg-slate-950/70 backdrop-blur-sm`.
- Dialog Container: Max width 4xl, max height 90vh, clear non-crushable header, scrollable body (`overflow-y-auto min-h-0`), sticky footer/close.
- Focus: Escape key and backdrop click close modal; close button prominently displayed in top-right with clear focus ring.

### Floating Utilities (Feedback / Language)
- The Feedback button must never obscure touch targets or content. On mobile, it must clear the bottom navigation bar and card content.

# DESIGN

The site should feel like **a new kind of personal website that happens to belong to a
developer**, not another developer portfolio. It should be premium, direct, intentional and
memorable, and never gimmicky. Visitors infer competence from evidence, so every claim should be
one click from its proof.

Colours are **not locked**. Phase 3 renders two directions and Odilbek chooses (D-024).

## 1. UX architecture

### Homepage (`/`)
- **It starts with the person, not a pitch:** the portrait composed with the name, one sentence
  of identity spanning software and languages, and current availability, location and local time.
- **Then a router** ("Where should we start?" is working copy, not final): 2–3 large, plain
  routes, each with a one-line blurb from `Profile.router_prompt` / `router_blurb`, leading to a
  role profile or `/about/`.
- **Below the router:**
  - an evidence strip of computed facts
  - a few featured projects across all profiles
  - a career map teaser (after Phase 11)
- **On mobile** the router follows the identity block directly, with full-width tap targets.

### Profile pages (`/<slug>/`)
- **Order:** hero → evidence strip → sections in their configured order → contact block.
- **Desktop:** a sticky in-page index built from section anchors.
- **Mobile:** a sticky bottom action bar with *Contact* and *Download CV* within thumb reach.
- **Hero variants** are generic, so any profile can use any of them. A profile may use its own
  photo or fall back to the default portrait:

| Variant | Composition |
|---|---|
| `portrait` | The photo leads; the claim sits beside it; the evidence strip is anchored to the photo's edge |
| `split` | Photo, claim and a live evidence panel ("last shipped…", availability) in one composition |
| `bilingual` | Photo plus the headline in two languages side by side |
| `statement` | Typographic only, for profiles where a photo adds nothing |

- **The photo on mobile is art-directed, not shrunk.** It uses a portrait-ratio crop from the
  stored focal point, sits below the name, and takes at most ~45% of the viewport height, so the
  first evidence or router is visible without scrolling.

### Project pages (`/projects/<slug>/`)
Informative and direct, **never a long case study**:
1. **Header:** title, one-line summary, status, dates, role, GitHub and demo buttons.
2. **At a glance:** stack chips linking to skill pages, context, timeframe.
3. **Body:** media, then a short description, then highlights as bullets.
4. **Related:** projects sharing skills, and the profiles the project appears on.

The back link returns to the referring profile (or the project's primary profile). Dashboard
character counters with recommended lengths keep descriptions short.

### Career map (Phase 11)
Built from existing relations; there is **no separate graph table**.
- **Columns:** Areas (skill categories) → Skills → Evidence (projects, roles, education) → Profiles.
- **Desktop:**
  - SVG curves are drawn from the selected node to its neighbours
  - hover or focus highlights a path
  - clicking opens a side panel (HTMX) with details and links
- **Mobile:** drill-down (Area → Skill → Evidence) with breadcrumbs, reusing the same partials.
- **Scoping:** on a profile page the map is limited to that profile's items, with a "show
  everything" toggle; `/map/` shows everything.
- **Base markup is nested lists of links**, so it works without JavaScript. JS adds lines,
  highlighting and arrow-key navigation.
- **Skill nodes show derived evidence:** "Django · 2021–now · 6 projects · 2 roles". Never bars.

### Profile switching
- **Desktop:** a persistent segmented control in the header, marked with `aria-current`.
- **Mobile:** the current profile is a header button that opens a bottom sheet of profiles, each
  with a one-line description.
- **Continuity:** switching keeps the current language, and cross-document View Transitions
  (CSS only, progressive enhancement) morph the header and title instead of hard-cutting.

### Mobile navigation
- A compact sticky header: monogram, profile switch, menu.
- Menu and switcher open as bottom sheets. There is no horizontal scrolling anywhere.
- Every screen is **designed at 375 px first**, then expanded. It is not the desktop layout shrunk.

### Dashboard UX
- **Layout:** a left sidebar on desktop (collapsible on mobile), with dense, calm lists that
  offer search, filters and inline publish toggles.
- **Editing:** edit pages with language tabs, "Save" plus "Preview as visitor", and an
  unsaved-changes guard.
- **Mobile:** messages and analytics are fully usable on a phone; heavy editing targets desktop.

## 2. Visual direction

A **personal dossier**: an editorial index rather than a landing page.
- a strong typographic hierarchy, generous whitespace and hairline rules
- monospaced metadata (dates, stacks, counts)
- minimal chrome, with no card soup, gradients or glassmorphism

**Two candidates**, compared in Phase 3 with the real photo:

| Direction | Character |
|---|---|
| **Editorial** | Serif display type with a Korean serif pairing; the portrait treated like a magazine profile |
| **Technical-minimal** | Grotesk type, a strict Swiss-style grid, a precise controlled crop |

**Signature idea: claims carry citations.** An intro can reference evidence, e.g.
`[[project:some-slug]]`, which renders a small citation chip linking to the proof. Competence is
inferred from the linked evidence rather than asserted.

### The photo without the template look
A prominent photo is the fastest route to "another portfolio" (D-023). Rules:
- **Compose the photo with the type:** a shared grid, with text aligned to the image edge.
  Never a round avatar or a floating cutout.
- **One photo per page**, never repeated in the header.
- **Consistent treatment** in light and dark: no drop shadows or glow, and colour grading
  settled once in Phase 3.
- **Evidence beside the face:** the first thing next to the photo is a fact, not a job-title word cloud.
- **Performance:**
  - `<picture>` with AVIF/WebP `srcset` and explicit `width`/`height` (no layout shift)
  - `fetchpriority="high"` and a preload on the hero image **only**
  - a budget of ≤ 200 KB hero bytes on mobile

## 3. Typography

The type must cover Latin, Hangul, and Uzbek `oʻ gʻ` (U+02BB). **All fonts are self-hosted**
(privacy, CSP, performance).

| Role | Candidate |
|---|---|
| Body / UI | **Pretendard Variable**: designed for mixed Korean/Latin text, OFL, dynamic subsetting via `unicode-range`, so visitors download only the glyphs they need |
| Display (editorial) | a Latin serif such as Newsreader or Fraunces, paired with MaruBuri for Korean |
| Display (technical) | Pretendard at heavy weights with tight tracking |
| Metadata | a monospace such as JetBrains Mono or IBM Plex Mono |
| PDF | the same families as local TTF/OTF files for WeasyPrint |

**Korean text:**
- `word-break: keep-all`, because otherwise Korean wraps in the middle of words
- a slightly taller line-height than Latin
- a `lang="ko"` attribute on Korean fragments inside other-language pages

**Headings and paragraphs:** `text-wrap: balance` on headings and `text-wrap: pretty` on paragraphs.

## 4. Space and layout

- A 4 px base scale; fluid section rhythm with `clamp()`; a fluid type scale (≈ 1.25 ratio).
- A reading width of about 68 characters.
- A 12-column desktop grid and a 4-column mobile grid.
- **Container queries** for components, so a component adapts to its slot, not the viewport.

## 5. Colour and theming

- **Semantic tokens in OKLCH:** `--bg --surface --text --muted --border --accent
  --accent-contrast`, defined for light and dark, with `color-scheme` set.
- **Theme toggle:** three states (system / light / dark) persisted in `localStorage`. A small
  nonce'd script in `<head>` prevents a flash of the wrong theme.
- **Profile accents** come from a small named token set applied with `data-accent`. Each accent is
  contrast-checked in both modes. **Tailwind class names are never built from database values.**

## 6. Components

- **Few, sturdy, server-rendered components** in `templates/components/`, included with
  `{% include … only %}`, each with a documented list of variants.
- **A component exists once there is a second use.** No speculative abstraction.
- A dev-only `/_styleguide/` renders every component × theme × language, and is where design
  review happens.

## 7. Motion

- **Timing:** 150–300 ms, animating only `opacity` and `transform`.
- **Motion must carry meaning:** state changes, navigation continuity (View Transitions), and
  map highlighting.
- **Never:** parallax, particles, WebGL, typing effects, scroll-jacking, or auto-play.
- `prefers-reduced-motion` disables all non-essential motion.

## 8. Accessibility (WCAG 2.2 AA)

**Structure and interaction**
- Semantic landmarks, a skip link, and visible `:focus-visible` rings.
- Targets of at least 24 px; information is never conveyed by colour alone.
- A correct `lang` on the page and on mixed-language fragments.
- The switcher, bottom sheets and career map are fully keyboard-operable.

**Forms, media and contrast**
- Forms have labels, inline errors and an error summary.
- **Alt text is required at upload.**
- Contrast is checked for every accent in both modes.

**Verification:** automated axe checks, plus keyboard and NVDA spot checks before launch.

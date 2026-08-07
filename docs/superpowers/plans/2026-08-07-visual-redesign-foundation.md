# StaffTrack Visual Redesign — Foundation & Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace StaffTrack's self-conflicting 1,067-line stylesheet with an ordered four-file design system in the approved "Clinic" direction, then rebuild the app shell and login screen on top of it.

**Architecture:** Bootstrap 5.3 stays for grid and JS; we override its visual layer. `custom.css` is split into `tokens.css` → `base.css` → `components.css` → `pages.css`, loaded in that order from `base.html` and `login.html`. Bootstrap's own utility colours (`bg-primary`, `text-white`, `table-dark`, etc.) are redefined against the new tokens so the 60+ existing templates inherit the new palette without being edited.

**Tech Stack:** Flask 3 + Jinja2, Bootstrap 5.3.2, Bootstrap Icons 1.11.1, Inter (Google Fonts), plain CSS with custom properties.

**Covers:** Phases 1 and 2 of the spec. Phases 3–6 (finance screens, dashboard, remaining pages, PDFs) get their own plan once this foundation is live.

## Global Constraints

- Presentation only — no route, model, template-logic or database change in this plan.
- No raw hex values in `base.css`, `components.css` or `pages.css`; read tokens from `tokens.css`.
- No `!important` except to override a Bootstrap utility, and every such case carries a comment saying why.
- No global element selector may set a property a component needs to control (this is the root cause of the two shipped contrast bugs).
- Semantic colour communicates state only; the accent never communicates state.
- All money and numeric columns use `font-variant-numeric: tabular-nums`.
- Every interactive element has a visible focus ring: 2px `--accent`, 2px offset.
- All transitions disabled under `prefers-reduced-motion: reduce`.
- Dark mode is explicitly out of scope.
- Stage files explicitly when committing; the working tree contains unrelated uncommitted quoting/pipeline work that must not be pushed.

---

### Task 1: Contrast audit script

The regression guard for the class of bug that shipped twice (dark headings on dark card headers; unreadable `NET COLLECTIONS` row). Written first so it can gate every later task.

**Files:**
- Create: `tools/check_contrast.py`

**Interfaces:**
- Produces: `contrast_ratio(fg_hex: str, bg_hex: str) -> float` and a CLI that exits non-zero when any declared pair falls below its threshold.

- [ ] **Step 1: Write the failing test**

Create `tools/check_contrast.py` with a `PAIRS` list of `(name, foreground, background, minimum)` tuples covering every foreground/background combination the design system declares, then:

```python
def contrast_ratio(fg_hex, bg_hex):
    def lum(h):
        h = h.lstrip('#')
        parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        parts = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    a, b = lum(fg_hex), lum(bg_hex)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
```

- [ ] **Step 2: Run it and confirm it reports on the current palette**

Run: `python tools/check_contrast.py`
Expected: prints a ratio per pair and exits 0 only if all pass.

- [ ] **Step 3: Commit**

```bash
git add tools/check_contrast.py
git commit -m "Add contrast audit for the design system palette"
```

---

### Task 2: `tokens.css`

**Files:**
- Create: `app/static/css/tokens.css`

**Interfaces:**
- Produces: every custom property consumed by `base.css`, `components.css` and `pages.css`. Names below are the contract; later tasks must use them verbatim.

- [ ] **Step 1: Write the token file**

```css
:root {
  /* Brand */
  --accent:        #1F5F4E;
  --accent-hover:  #17493C;
  --accent-wash:   #EAF2EE;
  --accent-line:   #C7DCD3;

  /* Ink */
  --ink:    #16211E;
  --body:   #4A5A55;
  --muted:  #6B7C77;
  --on-accent: #FFFFFF;

  /* Surfaces */
  --ground:    #F4F6F5;
  --panel:     #FFFFFF;
  --panel-alt: #FAFBFA;
  --line:      #E2E7E4;
  --line-soft: #EFF2F0;

  /* Semantic — state only, never decoration */
  --success: #1F7A4C;  --success-wash: #E6F2EB;
  --warning: #A9762A;  --warning-wash: #F7EFE1;
  --danger:  #9E3232;  --danger-wash:  #F6E7E7;
  --info:    #2A6480;  --info-wash:    #E6EFF4;

  /* Type scale */
  --t-xs: 11px; --t-sm: 12px; --t-cap: 13px; --t-base: 15px;
  --t-lg: 19px; --t-xl: 24px; --t-2xl: 31px;

  /* Shape */
  --r-control: 6px;
  --r-panel:   10px;
  --r-pill:    999px;

  /* Depth — cards use borders, not shadows */
  --shadow-pop: 0 8px 24px -12px rgb(22 33 30 / 0.28);

  /* Motion */
  --ease: 150ms cubic-bezier(0.4, 0, 0.2, 1);

  /* Layout */
  --nav-w: 248px;
}
```

- [ ] **Step 2: Add the new palette pairs to the contrast audit and run it**

Run: `python tools/check_contrast.py`
Expected: PASS for body-on-ground, muted-on-panel, on-accent-on-accent, and every semantic-on-wash pair.

- [ ] **Step 3: Commit**

```bash
git add app/static/css/tokens.css tools/check_contrast.py
git commit -m "Add design tokens for the Clinic direction"
```

---

### Task 3: `base.css` — reset, typography, layout shell

**Files:**
- Create: `app/static/css/base.css`

**Interfaces:**
- Consumes: all tokens from Task 2.
- Produces: `.sidebar`, `.sidebar-brand`, `.sidebar-nav`, `.sidebar-nav-link`, `.sidebar-nav-section`, `.sidebar-user`, `.main-content`, `.mobile-header`, `.page-header`, `.page-title`, `.page-subtitle` — the class names already used by `base.html`, so no template edits are required.

- [ ] **Step 1: Write the file**

Must contain, in this order: box-sizing reset; `body` on `--ground` with Inter and `--body`; the type scale bound to `h1`–`h6` with weight 650 and `letter-spacing: -0.02em`; `.text-muted` mapped to `--muted`; sidebar and mobile-header layout carried over from the current `custom.css` geometry but restyled (active nav = `--accent-wash` background with `--accent` text, no gradient, no shadow); `.main-content` with `margin-left: var(--nav-w)`; the existing responsive breakpoints at 991.98px and 575.98px; a global focus-visible ring; and a `prefers-reduced-motion` block disabling transitions.

Critically — the heading rule must NOT set colour on a bare selector. Use:

```css
h1, h2, h3, h4, h5, h6 {
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1.2;
  text-wrap: balance;
  color: inherit;          /* never a fixed colour; containers decide */
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/css/base.css
git commit -m "Add base layer: reset, type scale and app shell"
```

---

### Task 4: `components.css` — UI components and Bootstrap overrides

**Files:**
- Create: `app/static/css/components.css`

**Interfaces:**
- Consumes: tokens from Task 2.
- Produces: restyled `.card`, `.card-header`, `.card-body`, `.card-footer`, `.btn` variants, `.table`, `.badge`, `.alert`, `.form-control`, `.form-select`, `.form-label`, `.modal-content`, `.nav-tabs`, `.pagination`.

- [ ] **Step 1: Write the component layer**

Rules that must be present verbatim, because they fix the two shipped bugs at the root:

```css
/* Coloured card headers are retired. Any template still using
   .bg-primary/.bg-success/etc on a header renders as the neutral
   header instead of dark-on-dark. */
.card-header {
  background: transparent;
  border-bottom: 1px solid var(--line);
  color: var(--ink);
  font-weight: 650;
  padding: 1rem 1.25rem;
}
.card-header[class*="bg-"] {
  background: transparent !important;  /* override Bootstrap utility */
  color: var(--ink) !important;
}
.card-header[class*="bg-"] :is(h1,h2,h3,h4,h5,h6) { color: var(--ink); }

/* Table cells never receive a blanket colour, so variant rows
   (.table-dark, .table-success, ...) keep their own. */
.table > tbody > tr > td { color: inherit; }
```

Plus: `.table thead th` uppercase 11px on `--ground`; `tfoot`/`.fw-bold` totals row with `--line` top border and tabular figures; `.btn-primary` solid `--accent` with `--accent-hover`; `.btn-outline-*` mapped to `--line` borders; `.badge` variants mapped onto semantic wash/text pairs; `.alert` variants likewise; `.form-control:focus` with the `--accent` ring; and a block redefining Bootstrap's `.bg-primary`, `.bg-success`, `.bg-danger`, `.bg-warning`, `.bg-info`, `.bg-secondary`, `.bg-dark`, `.text-primary` … utilities onto the new tokens so untouched templates inherit the palette.

- [ ] **Step 2: Commit**

```bash
git add app/static/css/components.css
git commit -m "Add component layer with Bootstrap utility overrides"
```

---

### Task 5: `pages.css` and stylesheet swap

**Files:**
- Create: `app/static/css/pages.css`
- Modify: `app/templates/base.html` (stylesheet links)
- Modify: `app/templates/login.html` (stylesheet links)
- Delete: `app/static/css/custom.css`

- [ ] **Step 1: Write `pages.css`**

Login split-screen layout (`.login-shell`, `.login-pitch`, `.login-panel`, `.login-card`), dashboard stat cards, and the reconciliation/turnover money-table refinements.

- [ ] **Step 2: Swap the links in both templates**

Replace the single `custom.css` link with, in order:

```html
<link href="{{ url_for('static', filename='css/tokens.css') }}" rel="stylesheet">
<link href="{{ url_for('static', filename='css/base.css') }}" rel="stylesheet">
<link href="{{ url_for('static', filename='css/components.css') }}" rel="stylesheet">
<link href="{{ url_for('static', filename='css/pages.css') }}" rel="stylesheet">
```

- [ ] **Step 3: Delete the old stylesheet**

```bash
git rm app/static/css/custom.css
```

- [ ] **Step 4: Verify — templates compile and the e2e suite passes**

Run the template-compile check and the reconciliation/turnover e2e suite.
Expected: all templates compile; E2E ALL PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/static/css/pages.css app/templates/base.html app/templates/login.html
git commit -m "Swap StaffTrack onto the new four-file design system"
```

---

### Task 6: Login screen as a sales asset

**Files:**
- Modify: `app/templates/login.html`

- [ ] **Step 1: Rebuild the markup as a split screen**

Left: StaffTrack wordmark, a one-line description of what the product does, and three short proof points (daily reconciliation, per-practitioner turnover, role-based access). Right: the existing form, unchanged in field names, CSRF handling and error display — only its wrapper markup and classes change. Collapses to a single column under 900px with the pitch panel above the form.

- [ ] **Step 2: Verify login still works end to end**

Run the e2e suite (it logs in on every run).
Expected: E2E ALL PASSED.

- [ ] **Step 3: Commit**

```bash
git add app/templates/login.html
git commit -m "Rebuild the login screen as a product first impression"
```

---

### Task 7: Full verification and push

- [ ] **Step 1: Run the contrast audit**

Run: `python tools/check_contrast.py`
Expected: exit 0.

- [ ] **Step 2: Run the template compile check and e2e suite**

Expected: all templates compile; E2E ALL PASSED.

- [ ] **Step 3: Drive the app in a browser**

Log in, then visit the dashboard, daily reconciliation index/form/view, turnover reports, and analytics. Confirm no dark-on-dark text and no page scrolling sideways.

- [ ] **Step 4: Push**

```bash
gh auth switch --user drbuleni
git -c credential.helper= -c credential.helper='!gh auth git-credential' push
```

## Self-Review

**Spec coverage:** Palette → Task 2. Typography → Tasks 2, 3. Shape/depth/motion → Tasks 2, 3. Component rules → Task 4. File architecture → Tasks 2–5. Phase 1 → Tasks 1–5. Phase 2 → Tasks 3, 6. Verification → Tasks 1, 5, 6, 7. Phases 3–6 are deferred to a follow-up plan, as stated in the header.

**Placeholder scan:** No TBDs. Token file is complete and verbatim; the three bug-fixing component rules are given verbatim; remaining component rules are enumerated by selector and value source.

**Type consistency:** Token names in Task 2 match every reference in Tasks 3–5. Class names in Task 3 match those already present in `base.html`, so no template edits are needed beyond the stylesheet links.

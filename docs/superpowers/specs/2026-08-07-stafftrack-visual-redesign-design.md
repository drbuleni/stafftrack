# StaffTrack Visual Redesign — Design Spec

**Date:** 2026-08-07
**Author:** Vernon Sibiya (with Claude)
**Status:** Approved, ready for implementation

## Problem

StaffTrack works well but looks, in the owner's words, "childish, like a toy." It is about to
be sold to other dental practices, so the interface has to convince a stranger during a demo,
not merely serve staff who already use it daily.

The app is not badly built; it is visually undecided. Four specific habits cause most of the
damage:

1. **Saturated brights.** `#16a34a` green, `#0d6efd` blue and `#00e5e5` cyan appear on one
   screen. Primary colours at full saturation read as children's software.
2. **Colour as decoration.** Card headers are coloured because a colour was available, not
   because the colour means anything.
3. **Bootstrap's default fingerprints.** Gradient nav pills, layered shadows, 16px radii and
   stock button blues identify the app as a free template on sight.
4. **Money treated as ordinary text.** Figures share the weight, colour and alignment of a
   patient's surname, in an app whose main job is money.

A secondary, structural problem: `app/static/css/custom.css` is a single 1,067-line file that
fights itself. Two production bugs came from that — dark headings rendered on dark card headers,
and an unreadable `NET COLLECTIONS` row — both caused by a global rule overriding a component.

## Goal

One fixed, premium StaffTrack look, applied across every page, achieved by restraint and
precision rather than decoration. Expensive comes from subtraction.

## Non-goals

- **Dark mode.** Real ongoing maintenance cost, no user demand. Deliberately excluded.
- **Per-practice theming / white-label.** Decided against: the design stays under our control
  so it always demos well.
- **Removing Bootstrap.** The grid and JS are woven through 60+ templates. We override
  Bootstrap's visual layer instead; ripping it out is a separate project.
- **Changing any behaviour, route, or database field.** This is presentation only.

## Design system

### Palette

Named tokens; no raw hex values anywhere in component CSS.

| Token | Value | Use |
|---|---|---|
| `--accent` | `#1F5F4E` | Active nav, primary buttons, focus rings |
| `--accent-hover` | `#17493C` | Hover/active state of the above |
| `--accent-wash` | `#EAF2EE` | Active nav background, selected table rows |
| `--ink` | `#16211E` | Headings, money figures |
| `--body` | `#4A5A55` | Regular text |
| `--muted` | `#6B7C77` | Labels, secondary information |
| `--line` | `#E2E7E4` | Every border; hairlines replace shadows |
| `--line-soft` | `#EFF2F0` | Internal table row dividers |
| `--ground` | `#F4F6F5` | Page background |
| `--panel` | `#FFFFFF` | Cards, tables, form surfaces |

Semantic colours, deliberately desaturated relative to Bootstrap's defaults:

| Token | Value | Meaning |
|---|---|---|
| `--success` | `#1F7A4C` | Checked, approved, positive variance |
| `--warning` | `#A9762A` | Submitted, awaiting action |
| `--danger` | `#9E3232` | Negative amounts, deletion, errors |
| `--info` | `#2A6480` | Neutral notices |

Each semantic colour has a matching `-wash` background token at roughly 12% tint.

**Rule:** semantic colour communicates state only. It is never used to decorate a container.
The accent is never used to communicate state.

### Typography

Inter is retained — already loaded, and the correct face for dense financial data. The
improvement comes from using it deliberately.

- **Scale (fixed, 7 steps):** 11, 12, 13, 15, 19, 24, 31 px.
- **Headings:** weight 650, letter-spacing `-0.02em`, `text-wrap: balance`.
- **Uppercase labels:** 11px, weight 600, letter-spacing `0.08em`, `--muted`.
- **Money and all numeric columns:** `font-variant-numeric: tabular-nums`, right-aligned,
  `--ink` at weight 600; totals at weight 700 above a `--line` rule.
- **Body copy:** 15px / 1.6.

### Shape, depth, motion

- **Radii:** 10px panels and cards, 6px controls (buttons, inputs, selects), 999px for status
  pills only.
- **Shadows:** removed from cards entirely; borders carry separation. One soft shadow
  (`0 8px 24px -12px rgb(22 33 30 / 0.28)`) reserved for modals and dropdowns.
- **Gradients:** removed entirely.
- **Motion:** 150ms ease on hover/focus only. All transitions disabled under
  `prefers-reduced-motion: reduce`.
- **Focus:** a visible 2px `--accent` ring with 2px offset on every interactive element.

### Component rules

- **Card headers carry no background colour.** A bottom hairline and a weight-650 label
  replace the six coloured header variants in use today.
- **Tables:** header row in `--ground` with uppercase labels; body rows separated by
  `--line-soft`; totals row in `--ground` with a `--line` top border and weight 700; hover
  state `--accent-wash`.
- **Buttons:** solid `--accent` for primary; `--line` bordered on `--panel` for secondary;
  text-only for tertiary. One size scale, 6px radius, no shadows.
- **Status badges:** pill, semantic wash background, semantic text colour, 11px uppercase.
- **Forms:** `--line` border, 6px radius, `--accent` focus ring, label above input at 12px
  weight 600.

### File architecture

`custom.css` is replaced by four files loaded in strict order, so the cascade is predictable
and no file fights another:

| File | Contents | Approx. size |
|---|---|---|
| `css/tokens.css` | Custom properties only. No selectors beyond `:root`. | ~120 lines |
| `css/base.css` | Reset, typography, layout shell, sidebar, mobile nav. | ~280 lines |
| `css/components.css` | Buttons, cards, tables, forms, badges, alerts, modals, pagination. | ~480 lines |
| `css/pages.css` | Screen-specific rules: login, dashboard, reconciliation, turnover. | ~220 lines |

Rules for keeping the cascade clean:

- Component CSS reads tokens; it never hardcodes a colour.
- No `!important` except where overriding a Bootstrap utility is unavoidable, and each such
  case carries a comment explaining why.
- No global element selector may set a property that a component needs to control. Specifically,
  the two bugs above are fixed at the root: headings inherit colour inside coloured containers,
  and table cells never receive a blanket colour.

## Phases

Each phase is independently shippable and independently verifiable.

1. **Foundation.** The four stylesheets, replacing `custom.css`. Every page improves at once.
2. **Shell and login.** Sidebar, mobile header, and a split-screen login built as a sales
   asset: product name, one line on what StaffTrack does, clean form.
3. **Finance screens.** Reconciliation index/form/view, turnover index/form/view, analytics.
4. **Dashboard and KPIs.**
5. **Remaining pages.** Tasks, leave, SOPs, warnings, users, schedule, announcements, calendar,
   audit, receipts, performance, notifications.
6. **Documents.** `turnover_pdf.py` and `utils/exports.py` restyled to match.

## Verification

Every phase must pass, before commit:

1. **Template compile** — all templates render through the Jinja environment.
2. **End-to-end suite** — the existing reconciliation and turnover tests, covering create,
   edit, view, PDF, role gates and delete.
3. **Contrast audit** — a scripted check that no rule places text below 4.5:1 against its own
   background. This is the regression guard for the two production bugs described above.
4. **Visual check** — the affected pages driven in a real browser session.

## Risks

| Risk | Mitigation |
|---|---|
| Replacing `custom.css` breaks a page nobody thought to check | Phase 1 changes only presentation; the template-compile and e2e suites run before commit, and every phase is a separate commit that can be reverted alone |
| Bootstrap utility classes in templates (`bg-primary`, `text-white`) still carry old colours | `components.css` redefines Bootstrap's utility colours to the new tokens, so existing markup inherits the new palette without editing 60+ templates |
| Deploy risk to a live practice | Phases ship separately; reconciliation is exercised by the e2e suite on every one |
| Uncommitted quoting/pipeline work in the tree | Continue staging files explicitly, as with previous commits |

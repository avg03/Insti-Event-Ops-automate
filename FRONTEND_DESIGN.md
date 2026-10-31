# FRONTEND DESIGN — Warm professional event operations console

## Direction: Warm editorial operations, not cyberpunk AI
**Character:** trustworthy, organized, hospitable, grounded in real event work. Think cream paper, terracotta accents, forest-green confirmations, handwritten-feeling illustration accents (optional), generous whitespace and functional dense data cards.

Avoid pure black, luminous gradients, glassmorphism and overloaded agent chat windows.

### Palette
| Token | Hex | Usage |
|---|---|---|
| `background` | `#F7F4ED` | Warm ivory app background |
| `surface` | `#FFFEFA` | Cards |
| `surface-muted` | `#EFEAE0` | Subpanels, rows |
| `text-primary` | `#272D29` | Charcoal/olive ink |
| `text-muted` | `#757B73` | Secondary copy |
| `primary` | `#B85C38` | Terracotta CTA |
| `primary-dark` | `#8B432B` | Hover / deep accents |
| `green` | `#356B51` | Confirmed, verified |
| `amber` | `#C28B36` | Pending, held |
| `danger` | `#B54945` | Cancelled / blocked |
| `border` | `#E2DBCE` | Dividers |

**Fonts:** `DM Sans` (or system sans) for UI and `Fraunces` / `Georgia` for editorial headlines. Prefer locally available/system fonts if network blocked; never require font assets to run.

## Layout at 1440 px
```
┌───────────────┬─────────────────────────────────────────────────────────┐
│ EventOps      │  Breadcrumb / Event title                 [New event]    │
│ Overview      ├─────────────────────────────────────────────────────────┤
│ Events        │  Event summary (date, audience, budget)                  │
│ Guest desk    │  ┌───────────┬───────────┬───────────┬───────────┐     │
│ Vendors       │  │ Readiness │ Confirmed │ Budget    │ Recovery  │     │
│ Campaigns     │  └───────────┴───────────┴───────────┴───────────┘     │
│ Audit trail   │  ┌──────────────────────────┬─────────────────────┐     │
│               │  │ Agent execution timeline │ Budget allocation   │     │
│               │  │ live/simulated labels     │ Confirmed resources │     │
│               │  ├──────────────────────────┼─────────────────────┤     │
│               │  │ Guest coordination        │ Vendor bookings     │     │
│               │  └──────────────────────────┴─────────────────────┘     │
└───────────────┴─────────────────────────────────────────────────────────┘
```

### Screens
1. **Event intake:** compact form; input theme, audience, location, date, budget, venue limit, guest requirements, dietary needs; primary CTA **Organize event**.
2. **Operations overview:** current readiness, confirmed guest count, vendor commitments, cash budget, active critical issues, live execution timeline.
3. **Guest desk:** Crustdata candidate relevance/evidence cards; synthetic conversation drawer with negotiation terms and simulator confirmation badge.
4. **Procurement:** quotations matrix with quantity/capacity, latest total price, delivery cut-off, `HELD` vs `CONFIRMED`, contingency reserve and fees.
5. **Recovery panel:** injected failure type, old order invalidated, selected alternative, why chosen, new budget and verifier result. Make this the demo hero moment.
6. **Campaigns (P1):** editable event announcement, short-form reel storyboard and registration plan. Clearly draft-only.

### UI state and badges
- `READY_IN_SANDBOX`: moss-green check with exact text **Ready (sandbox)**.
- `PLANNING`: subdued ochre progress.
- `NEEDS_RECOVERY`: amber warning, show active issue count.
- `BLOCKED`: muted red and actionable blocker list.
- Crustdata-derived candidate identity: neutral pill `Verified source: Crustdata` when source really exists.
- Guest message/vendor booking: always pill `Simulated`.

### Important interactions
- Clicking `New event` opens form and posts to backend.
- Timeline polls `/api/events/{id}/timeline` (1–2 seconds in demo; pause when tab hidden optional).
- Clicking `Simulate vendor cancellation` calls simulator endpoint and shows recovery steps, then verifier output.
- Clicking candidate shows evidence source IDs and collected time; simulated invitations visible in separate tab.
- Budget card shows `committed`, `hold liability`, `fees`, `available`; do not double-count reserves as paid.
- Provide loading, API error and genuinely blocked states; don't fill UI with fake success.

### Responsive behavior
- Desktop: 240px sidebar + 2-column operations panel.
- Tablet: compact sidebar + one or two columns.
- Mobile: top navigation, stacked cards, wide CTAs, timeline first.

### Accessibility
- At least 4.5:1 contrast for body text, visible focus rings, semantic buttons, keyboard-accessible forms, meaningful text labels in addition to color, status announcements for updates.

## Demo-first UI principles
- Immediately show agent actions occurring, not an empty spinner.
- Keep identity provenance and simulator boundary visible in screenshots.
- Show **before and after cancellation** prominently.
- A beautiful dashboard is secondary to proving that real state changed.

Open [`frontend-preview.html`](frontend-preview.html) for the intended look and feel. It is intentionally a static illustrative concept, not a connected app.

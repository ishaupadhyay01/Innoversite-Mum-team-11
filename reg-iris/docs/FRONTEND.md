# Frontend (React + TypeScript + Tailwind)

Owner: **Team 4 — Frontend & Integration**. Stack: Vite 5, React 18, TypeScript 5 (strict), Tailwind 3,
TanStack Query 5 (server state), React Router 6, lucide icons, Vitest + Testing Library.

## Structure — by feature, mirroring the three backend modules

```
frontend/src/
  main.tsx                      QueryClient + root render
  App.tsx                       routes
  index.css                     Tailwind layers + small component classes (.input, .th, .td, .label)
  api/                          ← the ONLY place that knows URLs
    client.ts                   fetch wrapper: error envelope → ApiError, bearer token, query-string builder
    types.ts                    TypeScript mirrors of every backend schema
    ingestion.ts  search.ts  rules.ts
  components/
    layout/AppShell.tsx         sidebar nav, header, PageHeader
    layout/AlertBell.tsx        Alert Panel: polls /alerts (10 s), toast on new What's New
    ui/                         Button, Card/Stat, Badge/StatusBadge, Feedback (Spinner, ErrorBanner, EmptyState),
                                Pagination, FilePicker (drag & drop)
  features/
    dashboard/                  DashboardPage, WhatsNewCard
    documents/                  DocumentsPage, DocumentDetailPage (versions, activate, diff, clauses),
                                UploadDocumentDialog (duplicate check → match suggestions → upload)
    search/                     SearchPage (keyword/semantic toggle), FilterPanel (facets), SearchResultCard (citation)
    compare/                    ComparePage (any two versions), DiffView (+ test)
    impact/                     ImpactPage (3-step wizard), RunPage (stats + export), ImpactMatrixTable
  lib/                          format, useDebounce, download (token-aware CSV export)
```

## Routes
| Path | Page | Backend |
|---|---|---|
| `/` | Dashboard — KPI tiles, What's New cards, recent runs (`?card=` highlights a card from an alert) | ingestion, rules |
| `/documents` | Repository list | ingestion |
| `/documents/:id` | Version history, activate/rollback, clauses with page links, `?diff=` version diff | ingestion |
| `/search` | Clause search with filters and clickable citations | search |
| `/compare` | Compare any two versions / regulations | search (+ ingestion for pickers) |
| `/impact` | Wizard: document → rules JSON → trades CSV → run | rules, ingestion |
| `/impact/runs/:runId` | Stats, failures-by-rule chart, Impact Matrix (filters, sort, pagination), CSV export | rules |

## Conventions
* Server state only through TanStack Query; query keys are `[resource, ...params]`. Polling (`refetchInterval`) is
  used for processing versions, running analyses and alerts — swap for SSE/WebSocket later without touching pages.
* Components never call `fetch` directly; add a function in `api/*.ts` and a type in `api/types.ts`.
* Every async view handles loading (`Spinner`), error (`ErrorBanner` shows code + request id) and empty (`EmptyState`).
* Status colours are semantic tokens (`pass`, `fail`, `na`, `warn`, `brand`) in `tailwind.config.js`; never raw hex.
* Accessibility: labelled inputs, keyboard-operable file picker, `role="alert"` / `role="status"` for feedback.

## Running
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api → http://localhost:8080 (docker compose gateway)
npm run lint && npm run typecheck && npm test && npm run build
```
Set `VITE_API_TOKEN` if the APIs run with `API_TOKEN`.

## Backlog (Team 4)
- [ ] PDF viewer side panel (pdf.js) that opens at the cited page instead of a new tab
- [ ] Pivot-matrix view (`/runs/{id}/matrix`) as a heat-map tab on the run page
- [ ] Rule detail drawer: show JSONLogic, linked clause, confirm/override link (`PUT /rules/{id}/clause-link`)
- [ ] Optional Q&A chat panel (if the LLM tier is built) — answers must render their citations
- [ ] Playwright end-to-end smoke test in CI against the compose stack

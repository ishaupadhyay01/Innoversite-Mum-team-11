# Demo guide (about 4 minutes)

Everything below uses features that exist in the application and the supplied dataset. Numbers quoted are what the rule engine produces on `sample_trades.csv`.

## Before the demo

1. Fresh start: `docker compose down -v && docker compose up --build -d`.
2. Wait until `python scripts/verify_setup.py` prints PASS for every line (it also tells you how long start-up took on this machine).
3. Open http://localhost:3000 and http://localhost:8000/api/docs in two tabs.
4. Keep `demo/MiFID_II_2023_v3_DEMO.txt` at hand for the upload step. It is a clearly marked **synthetic** file (Paragraph 5 altered, Paragraph 8 invented) — say so when you upload it.
5. Do the search steps **before** the upload: afterwards the synthetic v3 becomes the latest MiFID II version and appears in "latest" search results.

`verify_setup.py` already runs one impact analysis, so the dashboard shows figures from the start. Running it again live is fine.

## Script

**1. Dashboard (20 s).** "This is the compliance overview, populated entirely from the supplied dataset: 7 regulatory documents in 10 versions from 7 regulators, every paragraph indexed in Elasticsearch, and the last impact analysis — 200 trades, 209 rule violations, 156 trades with at least one failure." Point to *What's new*: "These are the historical versions from the metadata, stamped with their original 2024 upload dates."

**2. Keyword search (45 s).** *Regulatory search* → type `Counterparty LEI` → Enter. "This is Elasticsearch BM25 — no AI. Matching terms are highlighted, and every paragraph has a citation: regulator, file, version and page." Open the top hit's **View source**: the original PDF opens at page 1 beside the extracted clause. Back. Show the result count and the milliseconds.
Try `"Mandatory Trade Reporting Fields"` in quotes: exact phrase. Optionally `FCA FX trades`: the FCA HTML section is cited as *Section #p3* — "HTML has no pages, so we never invent one."

**3. Filters vs keywords (20 s).** Tick *MiFID II* under Regulator. "Keywords decide relevance; metadata filters decide scope." Switch the scope to *All versions*: the same paragraph now appears from v1.0 as well, tagged *Historical version*, with "Identical text also appears in …".

**4. Version changes (30 s).** *What's new* → MiFID II v1.0 → v2.0 → *Compare versions*. "difflib aligns the clauses: six unchanged, one added — Paragraph 7, Execution Venue Disclosure, page 2." Mention EMIR v1.1: the comparison also shows that the EMIR v2 PDF contains a pasted copy of the Dodd-Frank text — a data issue the system surfaces instead of hiding.

**5. Upload and alert (40 s).** *Documents* → *Upload document* → drop `demo/MiFID_II_2023_v3_DEMO.txt`. The form recognises the MiFID II family and proposes v3.0. *Upload and index*: watch Queued → Processing → Indexed. A toast appears and the bell shows 1 unread. Open it: *New Version, Added Clause, Modified Clause* — "these labels only appear because the diff found them." *Compare versions* shows Paragraph 5 with the word-level change (15 → 10 minutes) and the new Paragraph 8.

**6. Impact analysis (30 s).** *Impact analysis* → *Run impact analysis* (all rule sets). "Eight JSON rules against 200 synthetic trades: 1,600 evaluations — 209 fail, 1,021 pass, 370 not applicable, zero errors." Point out NOT_APPLICABLE: "MiFID-3 and EMIR-1 only apply to derivatives, so equities aren't penalised."

**7. Inspect a violation (30 s).** Type `T000004` in the Trade ID box → open the MIFID-2 row. "Price is −99.9, which fails Price ≥ 0. Here is the trade record with the field highlighted, the rule's original JSON, what the engine actually evaluated, and the source: `rules_mifid.json#MIFID-2`. The rule files carry no document citation, so we show the related MiFID text found by keyword search and label it as informational." For a conditional failure, show T000007 / MIFID-3: "Because Asset_Class is Derivative, Maturity_Date is required, but it is missing."

**8. Export (10 s).** *Export filtered CSV* → open the file: backend-generated rows, formula-injection safe.

**9. API (25 s).** Switch to Swagger (`/api/docs`): one merged spec for all services. *Search → POST /api/search → Try it out* with `{"query": "negative price"}` → the SEC, CFTC and Dodd-Frank paragraphs that mention negative prices come back with citations. Optionally `POST /api/trades/query` with "Which trades are missing a Counterparty LEI?" → 18 trades, answered by structured filters rather than keyword search.

## If something goes wrong

- *Search returns 503* — Elasticsearch is still starting; *System health* shows it.
- *Upload says duplicate* — the demo file was uploaded already; `docker compose down -v` resets everything.
- *Dashboard has no analysis* — run it from *Impact analysis*.

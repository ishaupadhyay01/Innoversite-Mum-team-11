# Dataset findings (hackathon `sample_input/`)

Found while building and testing against the provided files. Each is handled in code; none required editing the data.

| # | File | Finding | How Reg IRIS handles it |
|---|---|---|---|
| 1 | `regulations/EMIR_2021_v2.pdf` | Page 2 contains **the whole Dodd-Frank document** appended after EMIR Paragraph 7 ("Dodd-Frank Act – 2022 … File name: Dodd_Frank_2022.pdf"), so clause numbers repeat. | Parser keeps both (`Paragraph 1 (#2)` …) and stores a **quality warning** on the version, shown in the UI. The EMIR v1→v2 diff therefore reports 8 added clauses, not 1. |
| 2 | `rules/rules_emir.json` — `EMIR-1` | Logic is `and[Asset_Class == "Derivative", ISIN present, ISIN regex]`, so **every non-derivative trade FAILS** (170 of 200). The description says it should only apply to derivatives. | Linter warns at upload ("scoping condition inside 'and'"). Fix without code: add `"applies_when": {"==": [{"var": "Asset_Class"}, "Derivative"]}` or rewrite as `{"if": [cond, check, true]}`. Kept as provided so results are faithful to the input. |
| 3 | `rules/rules_fca.json` — `FCA-2` | `if FX → true else (LEI and ISIN)` — so every **non-FX trade without an ISIN fails** (most equities/bonds, 132 of 200). Literal reading of the rule; probably not the intent. | FX trades are reported `NOT_APPLICABLE` (exemption branch). Flag to the business owner. |
| 4 | `rules/*.json`, `schema/reporting_schema.json` | `$` is escaped as `$$` (`"$$schema"`, `"^[0-9A-Z]{20}$$"`). | Schema loader un-escapes; `$$` in a regex is a harmless double end-anchor and the linter reports it as INFO. |
| 5 | `rules_mifid.json` — `MIFID-4` | `toNumber(substr(Timestamp, 0, 10)) >= "20180101"` — `"2024-06-25"` is not a number in standard JSONLogic. | `toNumber` converts ISO dates to `YYYYMMDD`; numeric-string comparison is coerced. T000005 (2017-12-31) fails as intended. |
| 6 | `rules/*.json` — `regex` | First argument is a **field name string** (`["Counterparty_LEI", "…"]`), not `{"var": …}`. | `regex` resolves a bare string that matches a trade field as a field reference; every schema field is always present in the evaluated trade (as `null` if empty) to avoid ambiguity. |
| 7 | `trades/sample_trades.csv` | 0 of the 163 format-valid LEIs pass the ISO 17442 checksum (synthetic data). ESMA ¶3 / FCA §5 require the GLEIF checksum. | `isValidLEI` operator is available; using it today would fail every trade, so the sample rules keep the format-only regex. |
| 8 | `metadata/doc_metadata.csv` | Dates are `DD-MM-YY`; regulator `Dodd‑Frank` uses a non-breaking hyphen (U+2011); `version` labels are not monotonic with file names (EMIR v2 file = `v1.1`). | Seed script parses dates; regulators are compared via `canonical_regulator()` (`DODD-FRANK`); version labels are free text, ordering uses `version_number`. |
| 9 | `rules/*.json` vs regulations | Regulator names in rules match metadata except for formatting; documents mention fields not in the schema (`Execution_Venue`, `Notional_Amount`, `Clearing_House`). | Linter warns when a rule references a field missing from the reporting schema. |
| 10 | `trades/sample_trades.csv` | Deliberate errors: 18 empty + 19 malformed LEIs, 8 negative prices, 8 zero quantities, 9 `XYZ` currencies, 1 pre-2018 trade, derivatives without maturity. | Reported twice: at upload (schema validation report) and per rule in the Impact Matrix with explanations. |

Baseline run (all three sample rule files, 200 trades × 8 rules = 1,600 checks):
**1,021 PASS · 374 FAIL · 205 NOT_APPLICABLE**; 186 of 200 trades have at least one failure
(dominated by findings 2 and 3).

# Rule files, operators and evaluation semantics

## File format

Each `data/rules/*.json` file is one rule set:

```json
{
  "regulator": "MiFID II",
  "jurisdiction": "EU",
  "rules": [
    {
      "id": "MIFID-3",
      "description": "If Asset_Class = Derivative, Maturity_Date is mandatory.",
      "logic": {"if": [{"==": [{"var": "Asset_Class"}, "Derivative"]}, {"var": "Maturity_Date"}, true]},
      "impact": "Derivatives need a Maturity_Date.",
      "severity": "high",
      "applies_when": {"==": [{"var": "Asset_Class"}, "Derivative"]},
      "citation": {"document": "MiFID_II_2023_v2.pdf", "clause": "Paragraph 4"}
    }
  ]
}
```

| Key | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique across all files |
| `logic` | yes | Expression; truthy = compliant |
| `description` | recommended | Shown everywhere |
| `impact` | no | Appended to failure explanations as "Rule impact: …" |
| `severity` | no | Shown when present; never invented |
| `applies_when` | no | Expression; when false the result is NOT_APPLICABLE |
| `citation` | no | Displayed verbatim as the rule's document citation. Without it the rule file is the authoritative source |

Add or change a file, then `POST /api/rules/reload` (or *Rules → Reload rule files*). No Python changes, no restart. `POST /api/rules/validate` checks a document first.

## Operators

| Operator | Arguments | Semantics |
| --- | --- | --- |
| `var` | `path` or `[path, default]` | Field value; dotted paths allowed; empty string → missing (`null`) |
| `and` / `or` | 1..n | Short-circuit, return the deciding operand |
| `not`, `!` | 1 | Negated truthiness |
| `!!` | 1 | Truthiness as boolean |
| `if`, `?:` | `[c1, v1, c2, v2, …, else]` | First truthy condition's branch |
| `==`, `!=` | 2 | Loose: numeric strings compare as numbers; `null == null` |
| `===`, `!==` | 2 | Strict type and value |
| `>`, `>=`, `<`, `<=` | 2 (`<`, `<=` also 3 = between) | Numbers (numeric strings coerced) or two strings (lexicographic); **missing operand → false**; number vs non-numeric string → ERROR |
| `in` | `[value, list or string]` | Membership (loose equality) or substring |
| `regex` | `[value, pattern]` | Python `re.search`; patterns ≤ 512 chars, validated at load time |
| `substr` | `[string, start, length?]` | JSONLogic semantics, negative start/length allowed |
| `toNumber` | `value` | Number from numeric string; **ISO date `YYYY-MM-DD` → integer `YYYYMMDD`** (extension, needed by MIFID-4); otherwise ERROR |
| `missing` | field names | List of missing field names |

Truthiness (JSONLogic): `null`, `false`, `0`, `""`, `[]` are false. There is no `eval`; unknown operators make the rule invalid and every evaluation of it an ERROR.

## Statuses

| Status | When |
| --- | --- |
| `NOT_APPLICABLE` | `applies_when` is false; or the top-level `if` selects a branch that is the literal `true` (the conditional requirement is not triggered, or is waived) |
| `PASS` | Logic is truthy |
| `FAIL` | Logic is falsy — explanation names the failing condition and actual values |
| `ERROR` | Invalid rule, or a value could not be evaluated (type mismatch). Never counted as compliant |

## Combining the selected rules (AND)

When several rules are selected for an analysis, they are combined with **AND** for each trade: a trade is compliant only if it satisfies *every* selected rule. Each rule is still evaluated and stored separately (the Impact Matrix keeps one row per trade × rule), and the combined verdict is derived from those rows:

| Overall | When |
| --- | --- |
| `FAIL` (non-compliant) | At least one selected rule fails — even if the others pass or error |
| `ERROR` (undetermined) | No rule fails, but at least one could not be evaluated |
| `PASS` (compliant) | Every selected rule that applies to the trade passes |
| `NOT_APPLICABLE` | None of the selected rules applies to the trade (counted as compliant, shown separately) |

A `NOT_APPLICABLE` rule (for example EMIR-1 on an equity trade) counts as satisfied, so selecting a derivatives-only rule never makes a non-derivative fail. Selecting no rules means all rules of the selected regulators. The rule files themselves are unchanged and are still evaluated with their own logic.

On the supplied data, all eight rules combined (`EMIR-1 AND EMIR-2 AND FCA-1 AND FCA-2 AND MIFID-1 AND MIFID-2 AND MIFID-3 AND MIFID-4`) give **44 compliant and 156 non-compliant trades**. Selecting only `EMIR-1 AND EMIR-2 AND FCA-1` gives 179 compliant and 21 non-compliant trades.

## Normalisation layer

The source JSON is never modified. A copy goes through generic normalisers; each change is listed under the rule (`normalization_notes`) in the API and UI.

| Normaliser | Trigger | Effect |
| --- | --- | --- |
| `regex_field_reference` | first `regex` argument is a string literal that exactly names a trade field | becomes `{"var": field}` |
| `regex_anchor_dedup` | pattern ends with `$$` | collapsed to `$` (equivalent in Python `re`) |
| `field_alias` | `var` path listed in the overlay's `field_aliases` | renamed (e.g. `Execution_Timestamp` → `Timestamp`) |
| `toNumber` note | logic uses `toNumber` | informs that ISO dates convert to `YYYYMMDD` |

`config/rules_overlay.json` holds reviewed, declarative additions: `field_aliases`, and per-rule `applies_when` with a written `rationale`, used only when the rule itself has no `applies_when`. It is data, not code. The supplied configuration contains exactly one entry:

- **EMIR-1** — `applies_when: Asset_Class == "Derivative"`. The description says "All derivatives must include a non-null Underlying_ISIN", but the logic embeds the derivative test inside an `and`, which would mark all 165 non-derivative trades non-compliant.

## Behaviour on the supplied rules (200 trades)

| Rule | PASS | FAIL | N/A | Notes |
| --- | ---: | ---: | ---: | --- |
| MIFID-1 valid LEI | 163 | 37 | 0 | 18 missing, 19 malformed |
| MIFID-2 price ≥ 0 | 192 | 8 | 0 | |
| MIFID-3 derivative needs maturity | 26 | 9 | 165 | if-branch `true` → N/A |
| MIFID-4 timestamp ≥ 2018-01-01 | 199 | 1 | 0 | T000005 (2017-12-31). The rule's impact text says such trades are "out of scope", but the logic expresses a failure, so it is reported as FAIL |
| EMIR-1 derivative ISIN | 30 | 5 | 165 | overlay applicability |
| EMIR-2 quantity > 0 | 192 | 8 | 0 | logic checks > 0 only (not "integer") |
| FCA-1 currency allow-list | 191 | 9 | 0 | `XYZ` |
| FCA-2 non-FX needs LEI and ISIN | 28 | 132 | 40 | Evaluated as written; equities, bonds and commodities have no ISIN in the data. Flagged rather than reinterpreted |

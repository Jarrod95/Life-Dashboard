# Spending Insights

The Spending page at `/finance/spending` now has a URL-backed Year/Month filter, category chart, cash flow, merchant leaderboard, discretionary opportunities, recurring candidates, savings assumptions and transaction explorer.

## API contract

New routes under `/api/v1/finance/spending/`:

- `periods` lists available years and months and returns the default latest data year.
- `summary?year=2026&month=10` includes `period`, decimal-string AUD figures, classification warnings and counts.
- `merchants?year=2026&month=10&sort=spend_desc` ranks merchants (bounded to 500).
- `insights?year=2026&month=10` returns conservative discretionary categories with evidence transaction IDs.
- `recurring?year=2026&month=10` returns at-least-three-observation cadence candidates.
- `cashflow?year=2026&month=10` is the period-specific cash-flow series.

Existing `/api/v1/finance/transactions`, `/finance/spending` and `/finance/spending/categories` accept `year` and `month`; existing `from` / `to` parameters take precedence over year/month for backwards compatibility. `month=all` means Jan–Dec. Invalid calendar numbers produce HTTP 400. The inclusive `end` in period metadata is a calendar date.

## Methodology and limitations

No financial files or personal data are bundled. Classification is rules-based, conservative and read-only. Payroll markers follow existing `effective_income` handling. Known transfers and repayment/BNPL references are excluded from consumption, but the full debit total is separately surfaced. Ambiguous BNPL transactions are flagged for reconciliation, not claimed as resolved or matched against purchases. Unknown expenses appear in total consumption and trigger a quality warning. Refund credits reduce their assigned category and are flagged for review. Only discretionary categories with two or more transactions produce savings opportunity cards. These are not assertions that purchases were unnecessary.

The recurring detector requires three or more roughly equally spaced transactions with amounts within 25% (or $2) of their average. Expected dates and equivalents are explicitly estimates. Historical comparisons, override persistence and robust statistical anomalies remain future work; do not interpret current opportunity cards as baseline-confirmed overspending.

The scenario slider supports 0–60% cuts in 5% increments. Year-to-date annualisation uses completed observed months where applicable, while a selected month is a hypothetical monthly baseline; neither proves future savings.

## Local validation

```powershell
python -m pytest tests/test_spending_insights.py -q
python -m pytest -q
```

Both Solarized themes should be checked at narrow and desktop widths. Manual QA: select a different year and month; check URL/back navigation, chart/category/merchant/table consistency; click category and merchant links; adjust/reset sliders; check no-data state; inspect transfers/BNPL in cash-flow versus consumption.

**Verification status:** Automated tests and screenshots have not been executed in the authoring environment. Do not merge until local tests and light/dark browser QA pass.

# Spending opportunity evidence and offset account projection

## Spending page

Each discretionary category now presents its period spend, transaction count, average ticket, specific rationale, confidence, and evidence of any available three-complete-month comparison. A category with insufficient baseline is explicitly labelled as such. A higher historical comparison alone does not establish unaffordable spending. Per-card sliders (0–60%, 5% steps) update shared hypothetical period, monthly and annual totals, replacing the duplicated calculator form.

Historical comparison: the calendar months immediately preceding the selected period are assessed for at least one classified transaction in each month. If coverage is incomplete or the selection is partial, percentage change is withheld. Per-category purchase frequency is a secondary descriptive signal. Baseline averages are not personal budgets.

## Offset graph

The new `GET /api/v1/finance/net-worth/offset` route returns history and a 12-month projection. It reads the `Net Worth Tracking` sheet from the same authorised local workbook or OneDrive Graph cache path used by mortgage tracking, matching `WBC Choice (Offset)` and configured alternative names. Values are taken from dated columns, with actuals shown as a solid line and projections as dashed.

Projection method: average calendar-normalized change across available consecutive historical observations in the 12 months leading to the latest record. Projected month-end dates are calendar safe and balances have a zero floor. No assumed transfers or interest credits are added. If only one observation exists, the projected change is zero, which is expressly not a meaningful trend. Current workbook/cache freshness governs the chart.

## Validation

Synthetic regression tests have been added in `tests/test_offset_spending_evidence.py`. Run locally:

```powershell
python -m pytest tests/test_offset_spending_evidence.py tests/test_spending_insights.py -q
python -m pytest -q
```

Manual QA: inspect Spending in Solarized light/dark, vary year/month, click transaction drill-downs, adjust/reset sliders, confirm no comparable baseline when prior months are absent; inspect Net Worth offset actual/projection line in both themes; compare latest offset balance with the Net Worth Tracking workbook; verify source not configured/missing states.

**Verification limitation:** The GitHub connector was available for repository changes, but a local repository checkout/browser was not available to run these tests or capture screenshots. The PR must remain draft until validation passes.

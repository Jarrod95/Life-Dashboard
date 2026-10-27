# JSON API

`GET /health` returns `{"status":"ok","application":"Life-Dashboard"}`.

Page routes: `/`, `/finance`, `/finance/net-worth`, `/finance/spending`, `/finance/budget`, `/finance/mortgage`, `/fitness`, `/health-dashboard`, `/goals`, `/settings/imports`.

Versioned endpoints:
- `GET /api/v1/overview` and `/finance/summary?as_of=YYYY-MM-DD`
- `GET /api/v1/finance/net-worth?from=&to=`, `/finance/net-worth/{snapshot_id}`
- `GET /api/v1/finance/transactions?from=&to=&category=&merchant=&account=&search=&page=1&page_size=50&sort=date&order=desc&include_transfers=true`
- `PATCH /api/v1/finance/transactions/{id}/category`, JSON `{"category_id":1}`
- `GET /api/v1/finance/spending?from=&to=&group_by=month|year|category|merchant`
- `GET /api/v1/finance/budget?fiscal_year=2026`, `/finance/mortgage`
- `POST /api/v1/finance/mortgage/scenarios`, JSON `{"principal":300000,"annual_rate":0.05,"offset":50000,"monthly_payment":2000,"extra_monthly_payment":0,"monthly_offset_topup":500}`
- `GET /api/v1/imports`, `/imports/{id}`
- `POST /api/v1/imports/finance/preview`, `/imports/finance` with multipart `file` (.xlsx)
- `GET /api/v1/fitness/summary`, `/health/summary`, `/goals`

Unknown money and unreconciled values are JSON null. Decimal amounts are strings. Import preview does not write to the DB. Mutations require Flask-WTF CSRF token from the HTML meta tag via `X-CSRFToken`. Errors use `{"error":{"code":"validation_error","message":"..."}}`. Page sizes are limited to 200.

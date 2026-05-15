# MagickVoice — Backend (FastAPI)

Phase 1: backend skeleton with SSL-verified Postgres, JWT auth, and role guards.

## Prerequisites

- Python 3.11+ (3.12 / 3.13 / 3.14 all work)
- Access to a managed PostgreSQL instance that requires SSL
- The instance's CA certificate as a `.pem` file

## Setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Configure

1. Copy the env template and fill in real values:

   ```bash
   cp .env.example .env
   ```

2. Place your managed-Postgres CA certificate at the path referenced by `DB_CA_CERT_PATH` (default: `./secrets/db-ca.pem`). The app refuses to start if the file is missing or invalid.

3. Generate a strong `JWT_SECRET`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

## Run migrations

From `backend/`:

```bash
alembic upgrade head
```

## Seed the default super admin

```bash
python -m app.seed
```

Creates `superadmin@magickvoice.com` / `Admin@123` (configurable via env). Idempotent — safe to re-run.

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

- Health check: <http://localhost:8000/health>
- OpenAPI docs: <http://localhost:8000/docs>

## Endpoints

### Auth (Phase 1)

| Method | Path           | Auth         | Notes                                |
|--------|----------------|--------------|--------------------------------------|
| GET    | `/health`      | public       | Liveness probe                       |
| POST   | `/auth/login`  | public       | Rate-limited 10/min/IP. Sets cookie. |
| POST   | `/auth/logout` | public       | Clears cookie.                       |
| GET    | `/auth/me`     | authed       | Returns the current user.            |

### Super Admin (Phase 2)

| Method | Path                         | Auth        | Notes                                                               |
|--------|------------------------------|-------------|---------------------------------------------------------------------|
| GET    | `/admin/dashboard/stats`     | super_admin | KPIs, 30-day series, top vendors, distributions, latest customers   |
| GET    | `/admin/vendors`             | super_admin | `?page&page_size&search&sort_by&sort_order`                         |
| POST   | `/admin/vendors`             | super_admin | Creates user + vendor in one transaction                            |
| GET    | `/admin/vendors/dropdown`    | super_admin | Lightweight `[ {id, name} ]` for pickers                            |
| GET    | `/admin/vendors/{id}`        | super_admin | Single vendor (joined with users.email)                             |
| PUT    | `/admin/vendors/{id}`        | super_admin | Partial update; optional password change; email uniqueness re-check |
| DELETE | `/admin/vendors/{id}`        | super_admin | Soft delete on both `vendors` AND linked `users`                    |
| GET    | `/admin/qr/{vendor_id}`      | super_admin | `?format=png\|jpeg\|svg&download=true\|false`                       |
| GET    | `/admin/qr/{vendor_id}/info` | super_admin | Returns `{vendor_id, vendor_name, url}` for preview                 |

### Vendor Admin (Phase 3)

| Method | Path                               | Auth         | Notes                                                        |
|--------|------------------------------------|--------------|--------------------------------------------------------------|
| GET    | `/vendor/dashboard/stats`          | vendor_admin | KPIs (today/week/month), 30-day series, distributions        |
| GET    | `/vendor/customers`                | vendor_admin | `?page&page_size&search&budget&looking_to_buy_in&sort_order` |
| GET    | `/vendor/customers/export`         | vendor_admin | CSV download of filtered customers                           |
| GET    | `/vendor/customers/filter-options` | vendor_admin | Canonical budget + buy-in lists for filter UI                |

All vendor endpoints derive `vendor_id` server-side from the JWT — the client never supplies it.

### Public (Phase 3)

| Method | Path                       | Auth   | Notes                                          |
|--------|----------------------------|--------|------------------------------------------------|
| GET    | `/public/vendors/{id}`     | public | Minimal `{id, name, city, state}` for register |
| POST   | `/public/customers`        | public | Rate-limited 5/min/IP. Re-validates vendor.    |
| GET    | `/public/options`          | public | Budget + buy-in option lists for chips         |

Public customer payload (server enforces 10-digit phone, canonical budget/buy-in):

```json
{
  "vendor_id": "uuid",
  "name": "Alice",
  "contact_number": "9876543210",
  "budget": "₹5-8L",
  "looking_to_buy_in": "This month"
}
```

QR code encodes `{HOSTING_ADDRESS}/register?vendor_id={UUID}`. When `download=true`, the response sets `Content-Disposition: attachment; filename="qr-<slug>-<uuid>.<ext>"`.

#### Password policy (vendor create / update)

- Min 8 characters
- At least one uppercase, one lowercase, one digit, one special character
- `password` must equal `confirm_password`

#### Pin code

Must be a 6-digit whole number (India). Stored as `DOUBLE PRECISION` per spec.

Login accepts JSON `{ "email": "...", "password": "..." }` and returns:

```json
{
  "user": { "id": "...", "email": "...", "user_type": "super_admin" },
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The same JWT is also set as an HTTP-only cookie (`mv_session`). Auth dependencies accept either the cookie or an `Authorization: Bearer <token>` header.

## Project layout

```text
backend/
├── alembic/                # migrations
│   ├── env.py
│   └── versions/0001_initial_schema.py
├── app/
│   ├── config.py           # pydantic-settings; reads .env
│   ├── database.py         # async engine, SSL ctx from CA pem
│   ├── main.py             # FastAPI app, CORS, security headers
│   ├── seed.py             # idempotent super-admin seed
│   ├── core/
│   │   ├── security.py     # bcrypt, JWT encode/decode
│   │   ├── deps.py         # get_current_user, require_role, get_current_vendor
│   │   └── rate_limit.py   # shared slowapi Limiter
│   ├── models/             # SQLAlchemy ORM (User, Vendor, Customer)
│   ├── routes/
│   │   ├── auth.py             # /auth/*
│   │   ├── admin_vendors.py    # /admin/vendors/*
│   │   ├── admin_dashboard.py  # /admin/dashboard/*
│   │   └── admin_qr.py         # /admin/qr/*
│   └── schemas/            # auth, vendor, dashboard
├── secrets/                # CA pem lives here (gitignored)
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Schema deviation from spec

`customers.contact_number` is `VARCHAR(15)` (not `DOUBLE PRECISION`). Floats lose leading zeros and precision for phone numbers, which would corrupt every record. Confirmed with the team before implementing.

## Scan tracking (added in Phase 3.5)

Each visit to `GET /public/vendors/{id}` (the API the register page calls on QR scan) inserts a `scan_events` row. The frontend MUST call this endpoint from a **client component** — server-rendered fetches would let link-preview crawlers (WhatsApp, Slack) and other JS-less bots inflate counts.

### `scan_events` schema

| Column      | Type          | Notes                                                         |
|-------------|---------------|---------------------------------------------------------------|
| id          | UUID          | PK, `gen_random_uuid()`                                       |
| vendor_id   | UUID          | FK → `vendors(id)`                                            |
| ip_hash     | VARCHAR(64)   | HMAC-SHA256(IP, IP_HASH_PEPPER) — 64 hex chars                |
| user_agent  | VARCHAR(512)  | truncated, nullable                                           |
| created_at  | TIMESTAMP     | NOT NULL, DEFAULT CURRENT_TIMESTAMP                           |

Indexes: `(vendor_id, created_at)`, `(created_at)`, `(vendor_id, ip_hash)`.

### Why HMAC with a pepper

`COUNT(DISTINCT ip_hash)` powers the "unique visitors" metric, so the **same IP must always hash to the same value**. HMAC with a server-side `IP_HASH_PEPPER` keeps it deterministic for grouping while making reversal infeasible without the secret. A per-row salt would prevent grouping; plain SHA-256 of an IP is reversible by a rainbow-table over the IPv4 space.

**Do not rotate `IP_HASH_PEPPER` after data exists** — rotation invalidates all historical unique-visitor counts.

### Metrics exposed

Dashboard responses now include, per window (all-time + current month):

- `total_scans` — raw event count (a reload counts again)
- `unique_visitors` — `COUNT(DISTINCT ip_hash)` over the window
- `conversion_rate` — `customers / unique_visitors` (0.0 if no visitors)

Plus `daily_scans_last_30_days` — zero-filled daily series for charting.

### Caveats

- `request.client.host` is used as the IP. Behind a trusted proxy, configure the proxy to overwrite `X-Forwarded-For` and adapt this read accordingly.
- Bot inflation isn't fully solved — having the frontend fire the request from `useEffect` is the main mitigation. Unique-visitor counting cuts through reload noise but not distinct-bot noise.
- Scan logging is best-effort: a DB failure on the scan insert is swallowed and the parent request still succeeds.

## Security notes

- Passwords hashed with bcrypt (cost 12).
- JWT is signed HS256; secret is read from env and never logged.
- HTTP-only cookie + `Authorization` header both supported.
- Soft-deleted users (`is_deleted = true`) cannot log in — filtered in the login query.
- `/auth/login` is rate-limited to 10/min per IP via slowapi.
- Security headers added globally (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS in prod).
- CORS restricted to `FRONTEND_ORIGIN`.

## What's next

- Phase 2: super admin endpoints (vendor CRUD, dashboard stats, QR generation)
- Phase 3: vendor + public endpoints
- Phase 4: Next.js frontend

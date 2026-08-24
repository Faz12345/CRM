# Dispatch — Support Ticketing CRM

A full-stack customer support ticketing system: create tickets, search and
filter them, and update status with notes as a ticket moves through your
queue.

**Stack:** Flask (REST API) · Jinja2 (server-rendered frontend) · MongoDB

## Features

- **Create tickets** — customer name/email, issue title, description. Ticket
  ID (`TKT-001`, `TKT-002`, …) and timestamps are generated automatically.
- **List all tickets** — clean table view: ID, customer, subject, status, date.
- **Search-as-you-type** — across name, ticket ID, email, and description,
  debounced and powered by the same JSON API used elsewhere.
- **Filter by status** — Open / In Progress / Closed, with live counts.
- **Ticket detail & update** — view full details, change status, and append
  timestamped notes (works with or without JavaScript).

## Architecture

```
run.py                  Entry point (loads .env, starts the app)
app/
  __init__.py            App factory + Mongo connection/index setup
  config.py               Env-driven configuration
  models/ticket.py        All MongoDB reads/writes live here
  routes/api.py            JSON REST API  (/api/tickets...)
  routes/views.py          Jinja2 page routes (/, /tickets/new, /tickets/<id>)
templates/                Jinja2 templates (base, index, create, detail, 404)
static/css, static/js     Styling + search-as-you-type client script
```

The API routes and the page routes both call the **same** functions in
`app/models/ticket.py`, so there is one source of truth for reading/writing
data — the JSON API isn't a bolt-on, it's what the search box calls under
the hood.

### Database (2 collections, matching the brief)

**`tickets`**
`ticket_id` (unique) · `customer_name` · `customer_email` · `subject` ·
`description` · `status` · `created_at` · `updated_at`

**`notes`**
`ticket_id` (references a ticket) · `note_text` · `created_at`

Ticket IDs are generated with an atomic `find_one_and_update` counter, so
concurrent ticket creation can never produce a duplicate ID.

### API Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/tickets` | `{customer_name, customer_email, subject, description}` | `{ticket_id, created_at}` |
| `GET` | `/api/tickets?status=&search=` | — | `[{ticket_id, customer_name, subject, status, created_at}, ...]` |
| `GET` | `/api/tickets/<ticket_id>` | — | full ticket + notes |
| `PUT` | `/api/tickets/<ticket_id>` | `{status?, notes?}` | `{success, updated_at}` |

Search matches are case-insensitive substring matches across
`ticket_id`, `customer_name`, `customer_email`, `subject`, and `description`.

## Running locally

**1. Get a MongoDB instance.** Easiest free option: [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)
(free M0 cluster), or run Mongo locally / in Docker:
```bash
docker run -d -p 27017:27017 --name mongo mongo:7
```

**2. Install dependencies**
```bash
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

**3. Configure environment**
```bash
cp .env.example .env
# edit .env and set MONGO_URI to your connection string
```

**4. Run**
```bash
python3 run.py
```
Visit `http://localhost:5000`.

**No Mongo handy?** Set `USE_MONGOMOCK=true` in `.env` to run against an
in-memory mock database — good for a quick look, but data won't persist
and this is not suitable for the deployed/graded instance.

### Authentication API

Authentication uses stateless Bearer JWTs. Register or log in, then send the
returned token as `Authorization: Bearer <token>` to access `/api/tickets`.

- `POST /api/auth/register` — create a user (`name`, `email`, `password`)
- `POST /api/auth/login` — receive an access token
- `GET /api/auth/me` — retrieve the current profile
- `PATCH /api/auth/profile` — update the current name or email
- `POST /api/auth/forgot-password` and `POST /api/auth/reset-password`
- `GET/PATCH /api/auth/admin/users...` — admin-only user management

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first production start to
bootstrap an administrator. Reset tokens are one-time, expire after one hour,
and are stored hashed. Keep `EXPOSE_RESET_TOKEN=false` in production and send
the token through an email provider; it is enabled locally only for testing.

#### SMTP password recovery

Set the SMTP variables in `.env` to send real reset emails. For Gmail, enable
2-Step Verification, create a Google **App Password**, and use that 16-character
value as `SMTP_PASSWORD` (do not use your normal Gmail password or a passkey).

Use `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USE_TLS=true`, your Gmail
address for `SMTP_USERNAME` and `MAIL_FROM`, and set `APP_BASE_URL` to the URL
where the CRM is running. Keep `EXPOSE_RESET_TOKEN=false` once SMTP works.

## Deployment (Railway)

1. Push this repo to GitHub.
2. On [Railway](https://railway.app), create a new project → **Deploy from
   GitHub repo**.
3. Add environment variables from `.env.example` (`SECRET_KEY`, `MONGO_URI`,
   `MONGO_DB_NAME`; leave `USE_MONGOMOCK` unset). For `MONGO_URI`, use a free
   [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) cluster —
   Railway's own Mongo plugin works too if you prefer.
4. Railway auto-detects the `Procfile` (`web: gunicorn run:app --bind
   0.0.0.0:$PORT`) and deploys. No further build config needed.

Render.com works the same way: same start command, same environment
variables, "Web Service" from the repo.

## What I'd add with more time

- **Auth** — right now anyone with the URL can create/update tickets; a real
  team needs agent accounts and an audit trail on who changed what.
- **Pagination** — the ticket list loads everything at once; fine for a
  demo, not for hundreds of tickets a day.
- **Multi-channel intake** — a `channel` field (email/chat/phone) and an
  `assigned_to` field so tickets can route to the right agent, which was the
  main "what would a real team need" gap I considered but scoped out to keep
  the core solid (see submission email for the one addition I did make).

## AI tool use

Built with AI assistance (Claude) for scaffolding and boilerplate; the
architecture, schema, and control flow decisions above are my own, and I
can walk through any part of the code on request.

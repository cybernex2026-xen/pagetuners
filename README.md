# PageTurner Books — Python + SQLite + Vercel

A Python FastAPI bookstore using SQLite-compatible storage. Local development uses Python's built-in `sqlite3`; Vercel production uses a hosted SQLite-compatible libSQL database through the Python `libsql` client.

## Catalogue preserved

The seed catalogue contains **101 original books**: the original 100 catalogue books plus the 101st featured title, **Waruni Sanhithaka Mala** by N.D. Wickramasinghe (200 pages, LKR 10,000). Its original cover remains at `public/assets/waruni-cover.jpg`, and the supplied display/banner image remains at `public/assets/waruni-book-display.jpg`. The other 100 catalogue books each have their own generated thumbnail. Stable seed IDs and `INSERT OR IGNORE` prevent duplicate inserts and avoid overwriting existing database entries.

## Local development (Windows)

1. Install Python 3.11+.
2. In PowerShell, from the project folder:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. Leave `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` unset. The app automatically creates `pageturner.db` in the project folder using Python's built-in SQLite.
4. Open `http://127.0.0.1:8000`.

The local database file persists on your computer. Back it up regularly.

## Vercel deployment with persistent SQLite-compatible storage

**Important:** Vercel Functions are serverless. A SQLite file written to a function's local filesystem is temporary and is not a reliable shared database across deployments or function instances. For persistent multi-customer orders on Vercel, use a hosted SQLite-compatible libSQL database (for example, Turso). The application remains Python-backed and uses SQLite-compatible SQL; it does not use PostgreSQL.

1. Create a Turso/libSQL database and generate an auth token.
2. Push this project to GitHub and import the repository into Vercel.
3. Add these Vercel environment variables:
   - `TURSO_DATABASE_URL` — database URL, normally beginning with `libsql://`.
   - `TURSO_AUTH_TOKEN` — database auth token.
   - `ADMIN_KEY` — a long, unique secret.
4. Deploy and visit `/api/health`. It should report `database: sqlite` and `books: 101`.

When the Turso variables are present, Python connects to the hosted SQLite-compatible database. Without them, it falls back to a local SQLite file, which is for local development only and is not persistent on Vercel.

## Store features

- Responsive catalogue, search, category filtering, sorting and cart.
- Checkout with customer contact and delivery details.
- Cash-on-delivery order creation; prices are re-read from the database on the server.
- Orders stored in SQLite-compatible storage with unique order references.
- Protected custom-book creation/deletion and protected order listing.

The site does not collect card details or process online card payments. A payment provider and verified server-side payment callbacks are needed before accepting online payments.

## Admin API

Set `ADMIN_KEY` in the environment and send it as the `X-Admin-Key` header:

- `POST /api/books` — add a custom book.
- `DELETE /api/books/{book_id}` — delete a custom book. Original seed books cannot be deleted.
- `GET /api/admin/orders` — view the latest 200 orders.

## API

- `GET /api/health`
- `GET /api/books`
- `POST /api/books`
- `DELETE /api/books/{book_id}`
- `POST /api/orders`
- `GET /api/admin/orders`

Before opening publicly, add real shipping/returns/privacy policies, configure database backups and rate limiting, and test checkout. Checkout is currently cash on delivery only.

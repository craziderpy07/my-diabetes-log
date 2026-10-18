# My Diabetes Log

A responsive Flask web app for organizing glucose, meal, exercise, and medication records into one chronological timeline. **Educational prototype: use synthetic data only. Not a medical device or treatment tool.**

## Features
- Account registration with a unique username and email; log in with either one; password hashing and per-user record ownership
- Personal Information page: click Edit to change username/email, or Update Password to set a new password. Saves to PostgreSQL without reloading the page
- Create, view, edit, and delete records
- Date and category filters, glucose summary
- Algorithm implementations: min-heap k-way merge, binary-search date ranges, hash-map grouping, two-pointer rolling averages
- Neon-hosted PostgreSQL via SQLAlchemy
- CSRF-protected forms and server-side validation

## Local setup (Windows PowerShell)
1. Create a [Neon](https://neon.tech) PostgreSQL database and copy its connection string.
2. Open this folder in VS Code.
3. `py -m venv .venv`
4. `.venv\Scripts\Activate.ps1` (or use VS Code's selected virtual environment)
5. `pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and set `DATABASE_URL` and a random `SECRET_KEY`. Never commit `.env`.
7. `flask --app app init-db` (re-run this after upgrading: it adds the new `username` column to an existing database)
8. `flask --app app run --debug`
9. Open `http://127.0.0.1:5000`, create an account, and enter fictional sample records.

On macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate` and use the same Flask commands.

## Deploying on Vercel
1. Put the project on GitHub (`.env` is ignored, so your secrets are not uploaded).
2. On vercel.com choose **Add New Project**, import the repository, and add these environment variables:
   - `DATABASE_URL` - your Neon connection string (Neon's pooled connection string works best)
   - `SECRET_KEY` - a long random value
   - `COOKIE_SECURE` = `1`
   - `FLASK_DEBUG` = `0`
3. Click **Deploy**. Vercel detects Flask automatically.
4. Create the tables once from your own computer: put the same `DATABASE_URL` in your local `.env` and run `flask --app app init-db`.

The stylesheet is in `public/style.css` because Vercel serves static files from the `public/` folder.

## Tests
`python -m pytest -q`

## Design notes
- Dates and times are entered and shown in Pacific time (labelled PST), as MM/DD/YYYY and HH:MM AM/PM. They are stored as UTC and follow Pacific daylight saving rules (the `tzdata` package supplies time zone data on Windows).
- The timeline loads the current user's rows, sorts each category in PostgreSQL, and merges four sorted streams using a min-heap. For very large datasets, add pagination and streaming queries.
- The rolling glucose averages use an inclusive 60-minute time window over selected readings. They are exploratory statistics, not clinical recommendations.
- `init-db` is for initial development. Use database migrations for later schema changes.

## Security limitations
This is a learning prototype, **not ready for real patient health data or public production deployment**. Before that, add email verification, rate limiting, password recovery, session protections, auditing, data export/deletion, security review, operational monitoring, and appropriate regulatory/privacy safeguards. Keep `FLASK_DEBUG=0` and use HTTPS and secure cookies in any deployed environment.

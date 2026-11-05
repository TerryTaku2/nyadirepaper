# Nyadire College Past Papers Portal (with backend)

FastAPI + SQLite backend that also serves the existing web page. Accounts, intakes, papers and
announcements are now stored on the server and shared across every device.

## Run it

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. API docs: http://localhost:8000/api/docs

**First start:** two admin accounts are created (`superadmin` = Ultimate Admin, `admin` = standard).
If you don't set passwords through environment variables, random ones are generated, printed once
in the console and saved to `backend/data/initial_admin_credentials.txt` - log in, then delete that file.
To choose your own, see `backend/.env.example` (`NYADIRE_ULTIMATE_PASSWORD`, `NYADIRE_ADMIN_PASSWORD`).

## What changed from the prototype
| Before (browser only) | Now |
|---|---|
| Admin passwords written in `index.html` | Stored hashed (scrypt) in the database; never sent to the browser |
| Student passwords visible to the admin | Hashed; admin sees only "Login ready / Not registered" |
| Data in each browser's localStorage / IndexedDB | SQLite database + PDF files on the server (`backend/data/`) |
| Anyone could read papers by editing the page | Papers/announcement PDFs only download for logged-in students (own programme) or admins |
| Hard-coded test student `lavmoe` | Removed |

## How the student flow works
1. Admin adds a student to an intake with a **temporary password** (e.g. `1947`) - one at a time or by CSV.
2. Student clicks *Create account*, enters their ID + temporary password, their name and a new password (min 6 chars).
3. Student signs in. "Unregister" (admin) resets them to the temporary password `1947`
   (`NYADIRE_REGISTRATION_PASSWORD`) and signs them out.

## Security built in
- scrypt password hashing; sessions are random tokens in `HttpOnly`, `SameSite=Strict` cookies (hash stored server-side)
- 5 failed logins per IP+username -> 15 minute lockout
- Cross-origin write requests rejected; uploads must be real PDFs (magic-byte check), size-limited, stored under random names outside the web root
- Ultimate Admin can reset the standard admin's password; any admin can change their own (`POST /api/admin/change-password`)

## Going live checklist
- Serve over **HTTPS** and set `NYADIRE_COOKIE_SECURE=true`
- Back up the whole `backend/data/` folder (database + uploaded PDFs)
- Run a single uvicorn worker (or move the login throttle to a shared store before scaling out)
- Behind a reverse proxy (nginx/Caddy): run uvicorn with `--proxy-headers` so lockouts use the real client IP

## Tests
```bash
cd backend && python -m pytest tests -q
```

## Layout
```
backend/app/    main.py (app) | auth.py | admin.py (intakes, students) | content.py (papers, announcements)
                db.py (schema, seeding) | security.py (hashing, throttle) | config.py
backend/tests/  API tests (19)
backend/sample_papers/   the three sample PDFs from the old zip (not publicly served; upload via the admin page)
static/         index.html + app.js (front-end) + assets/
```

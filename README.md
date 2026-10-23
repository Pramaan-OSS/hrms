[![CI](https://github.com/Pramaan-OSS/hrms/actions/workflows/ci.yml/badge.svg)](https://github.com/Pramaan-OSS/hrms/actions/workflows/ci.yml)

# HRMS

Everyday HR and payroll: employees, attendance and shifts, leave, expenses,
recruiting, performance and payroll — in one self-hosted app.

## Quick start

1. Install Docker with Compose.
2. `cp .env.example .env` and paste your key: `PRAMAAN_API_KEY=...`
3. `./start`

When the stack is healthy, open the printed local address and sign in with the
generated administrator credential (its location is printed, never the value).

## What it needs

- `PRAMAAN_API_KEY` is the only value a person types. Everything else in
  `.env.example` has a working default or is generated on first run.
- Without a key, the app runs: sign-in, employee data, attendance, leave and
  the rest keep working. Actions that go through Pramaan show one plain
  "not available yet" message until the key is set.
- Optional connected features (calendar events, meeting rooms, text notices,
  document reading, identity checks, payouts, assessments) are off until their
  handles are set in HR Settings.

## Tests

- Contract and integration checks (no server needed):
  `python3 -m unittest discover -s review -p 'test_*.py'`
- The full backend suite runs on a disposable site inside the compose stack.

## Licence

This template is licensed under AGPL-3.0 (see `LICENSE`). The original
program's GPL-3.0 notice is preserved in `LICENSE-ORIGINAL` with all its
copyright notices.

## Built on

This product is built on [Frappe HR](https://github.com/frappe/hrms) by
Frappe Technologies and contributors, licensed GPL-3.0. Thanks to its
community; the original licence text and copyright notices are preserved in
`LICENSE-ORIGINAL`.

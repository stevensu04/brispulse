# Deploying BrisPulse

The first release is **live-only**: one container holding the API, the collector and the
web app, with no database ([Architecture §19](BRISPULSE-ARCHITECTURE.md)). It is set up
to run on [Render](https://render.com)'s free web service.

**Live at https://brispulse.onrender.com** (deployed 2026-11-17 from `main`, commit `bcd9943`).

## What to expect from the free tier

Render's free web service has 0.1 CPU and 512 MB of memory and **spins down after 15
minutes without inbound visits** ([Render docs](https://render.com/docs/free)).

| Measured here, with the image limited to Render's free CPU and memory | |
| --- | --- |
| Web server answering | 17 s after the container starts |
| Timetable loaded | 43 s |
| Live data on screen | 46 s |
| Memory used | 110 MiB of 512 MiB |

**Measured on Render itself** (one cold start, 2026-11-17 22:22 Brisbane time, after the
service had been idle): the first request was answered after **23 s**, and all three feeds
were live **35 s** after that first request. So a visitor arriving after a quiet spell waits
about half a minute, and the app shows a "Waking up" screen meanwhile. One measurement:
expect it to vary.

## Setup (done once)

The Render account and the GitHub link were created by the owner. The service was then created from the Blueprint:

1. **New → Blueprint** on Render, repository `stevensu04/brispulse`, branch `main`.
   Render reads [`render.yaml`](render.yaml) and creates one service named `brispulse`.
2. Blueprint name `brispulse`; path `render.yaml`.
3. The first build took about a minute and a quarter.

No environment variables or secrets are needed. Render's Blueprint page shows "Hobby" as the workspace plan; the service itself is on the Free instance type.

## Checking a deployment

- `/healthz` returns `{"status":"ok"}` as soon as the process is up.
- `/api/v1/status` shows each feed's state. All three should read `live` within about a
  minute of a cold start.
- `/` is the dashboard.

Checked after the first deploy: `/healthz` returned `{"status":"ok"}`, `/api/v1/status` reported all three feeds `live`, and the map showed about 995 vehicles.

All of that is automated. From `backend/`:

```bash
uv run python -m brispulse.smoke https://brispulse.onrender.com
```

It waits for a sleeping host to wake, then checks that the process is up, the web app is
served with its security headers, all feeds turn live, and the overview has data. It prints
one line per check and exits 1 if any fails.

The same check runs **every day at 08:00 Brisbane time** as the GitHub Actions workflow
`Smoke check (live site)` (`.github/workflows/smoke.yml`), and can be started by hand from
the Actions tab. When a scheduled run fails, GitHub emails the person who last changed the
workflow's schedule. Each run wakes the free host once.

## Updating

Every commit to `main` redeploys (`autoDeployTrigger: commit`).

## Operations

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| "Waking up" for about half a minute | The free host was asleep | Nothing; this is expected |
| A feed shows *Stale* or *Unavailable* | TransLink's feed is late or down | Check `/api/v1/status` (`last_attempt_outcome`). The app keeps serving the last data with a warning and withholds it after the limit. Nothing to fix on our side |
| "Waking up" never ends | The timetable download from TransLink failed at start-up | The service retries every 30 s. If it persists, check Render's logs for `static` errors and whether `https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip` answers |
| The site does not answer at all | The deploy failed, or Render suspended the free service (750 free hours a month, or bandwidth limits) | Render dashboard → the service's Events and Logs |
| A bad deploy | A change on `main` broke something | Render dashboard → Deploys → roll back to the previous deploy; then revert the commit on `main` |

Logs are in the Render dashboard (service → Logs). The service logs every failed fetch.

The dependencies are audited weekly by the `Dependency audit` workflow
(`.github/workflows/audit.yml`).

## Before announcing it publicly

- Done 2026-11-17: emailed `translink.opendata@tmr.qld.gov.au` with contact details and the
  intended use, asking for approval and the attribution wording they expect. **Waiting for
  their reply.** If they ask for changes, the attribution text is in
  `backend/brispulse/api/views.py` (`ATTRIBUTION`, `DISCLAIMER`) and on the About page.
- Done 2026-11-17: the portfolio page now describes the deployed app and links here.

## If you later want history

Run it on a host that never sleeps and set `DATABASE_URL` to a PostgreSQL database; the
history code switches on by itself. See [`backend/README.md`](backend/README.md).

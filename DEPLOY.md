# Deploying BrisPulse

The first release is **live-only**: one container holding the API, the collector and the
web app, with no database ([Architecture §19](BRISPULSE-ARCHITECTURE.md)). It is set up
to run on [Render](https://render.com)'s free web service.

## What to expect from the free tier

Render's free web service has 0.1 CPU and 512 MB of memory and **spins down after 15
minutes without inbound visits** ([Render docs](https://render.com/docs/free)).

| Measured here, with the image limited to Render's free CPU and memory | |
| --- | --- |
| Web server answering | 17 s after the container starts |
| Timetable loaded | 43 s |
| Live data on screen | 46 s |
| Memory used | 110 MiB of 512 MiB |

On top of that comes Render's own wake-up, which its docs put at about a minute. **A
visitor arriving after a quiet spell should expect to wait one to two minutes.** The
app shows a "Waking up" screen meanwhile. These are local measurements with a CPU cap,
not measurements on Render itself; check them after the first deploy.

## One-time setup (needs your own Render account)

An account, and the link between Render and your GitHub, can only be created by you.

1. Create an account at <https://render.com> (sign in with GitHub).
2. **New → Blueprint**, choose the `stevensu04/brispulse` repository, branch `main`.
   Render reads [`render.yaml`](render.yaml) and proposes one service named `brispulse`.
3. Approve it. The first build takes a few minutes.
4. Open the address Render gives you (`https://brispulse-….onrender.com`).

No environment variables or secrets are needed.

## Checking a deployment

- `/healthz` returns `{"status":"ok"}` as soon as the process is up.
- `/api/v1/status` shows each feed's state. All three should read `live` within about a
  minute of a cold start.
- `/` is the dashboard.

## Updating

Every commit to `main` redeploys (`autoDeployTrigger: commit`).

## Before announcing it publicly

- Email `translink.opendata@tmr.qld.gov.au` with your contact details and ask what
  attribution wording they expect (their open-data terms require this). The dashboard's
  About page already carries a CC BY 4.0 attribution and a no-endorsement disclaimer.
- The portfolio page for BrisPulse still describes the earlier concept and should be
  updated to point at the deployed app and this repository.

## If you later want history

Run it on a host that never sleeps and set `DATABASE_URL` to a PostgreSQL database; the
history code switches on by itself. See [`backend/README.md`](backend/README.md).

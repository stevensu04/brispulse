# BrisPulse web app

The dashboard, live at https://brispulse.onrender.com: React and TypeScript, built with Vite. It reads only the BrisPulse API
(`/api/v1`) and holds no data of its own.

## Run it

Start the backend first (see [`../backend/README.md`](../backend/README.md)); the
live-only mode needs no database:

```bash
cd ../backend && uv run uvicorn brispulse.main:app
```

Then, from this folder:

```bash
npm install
npm run dev
```

The dev server proxies `/api` to the backend on port 8000.

To see it exactly as it is deployed, build it and let the backend serve it:

```bash
npm run build
cd ../backend && BRISPULSE_WEB_DIR=../frontend/dist uv run uvicorn brispulse.main:app
```

## Checks

```bash
npm run typecheck
npm test
npm run build
```

## Layout

```
src/
  api/          client.ts (the only code that calls the API), hooks.ts, schema.d.ts
  lib/          formatting, the hash router, theme, delay-band limits
  components/   freshness badge, loading/starting/unavailable/error states, delay bar
  views/        Overview, MapView, Routes, RouteDetail, TripPanel, Alerts, About
  styles/       tokens.css (colours by role, light and dark), app.css
```

`src/api/schema.d.ts` is generated from `backend/openapi.json`. When the API changes:

```bash
cd ../backend && uv run python -m brispulse.openapi > openapi.json
cd ../frontend && npm run api:types
```

CI fails if either file is out of date, so the app's types cannot drift from the API.

## Rules the interface follows

- **Never a zero for something unknown.** When the API withholds a value (`null`), the
  app says "Unavailable" and shows the API's reason.
- **Freshness is always visible**, as an icon and a word as well as a colour.
- **Delay is always in words** ("4 min late"), and described as a prediction.
- **Every state has a screen**: loading, waking up, unavailable, error, empty.
- Colours come from `tokens.css` by role. The delay colours (early, within band, late)
  and the freshness colours are separate sets and are not reused for anything else.

## The map

[MapLibre GL JS](https://maplibre.org/) with tiles from
[OpenFreeMap](https://openfreemap.org/) (OpenStreetMap data; free, no key or account;
attribution is shown on the map). It is a third-party service with no guarantee: if it
is unreachable the vehicles still draw, on a blank background.

The map library is loaded only when the map is opened, because it is large (about
290 kB compressed).

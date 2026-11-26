# Spotter: Weather-Aware Truck Routing

Spotter helps a truck driver choose the safest route based on weather, load weight and travel time. Enter an origin, destination, departure time and load weight. The app generates up to three routes, checks the weather along each one **at the time the truck is expected to be there**, scores the risk, recommends a route and shows a 0–48 hour weather heatmap along the trip corridor.

**Stack:** React 18, TypeScript, Vite and MapLibre GL on the front end; Django 5.2 and Django REST Framework on the back end. No API keys and no database.

## Contents

- [Features](#features)
- [Quick start with Docker](#quick-start-with-docker)
- [Using the app](#using-the-app)
- [Configuration](#configuration)
- [How it works](#how-it-works)
- [API reference](#api-reference)
- [Error handling](#error-handling)
- [Project structure](#project-structure)
- [Local development without Docker](#local-development-without-docker)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Assumptions and limitations](#assumptions-and-limitations)
- [Data and attribution](#data-and-attribution)

## Features

**Trip planning**
- Place search with autocomplete and keyboard navigation. Typed text that wasn't picked from the list is resolved to the best match on submit.
- Swap origin and destination in one click.
- Departure date and time (defaults to the next full hour; up to 14 days ahead).
- Load weight by typing, presets (10k, 30k, 40k, 80k lb) or slider, limited to 80,000 lb.
- Weather checkpoints every 10, 25 or 50 miles, or chosen automatically from trip length.

**Routes and risk**
- Up to three distinct route options.
- Weather sampled at every checkpoint using the truck's estimated arrival time there.
- Wind, rain and snow risk levels with the load-weight rules applied.
- A recommended route with plain-language reasons, and a **Travel not advised** warning when even the best route crosses No Travel conditions.
- Route cards with travel time, distance, arrival, average risk, peak risk, a miles-by-risk bar and a summary, tagged **Recommended**, **Fastest** or **Shortest**.
- Checkpoint table with mile marker, ETA, wind, rain, snow and risk, flagging checkpoints raised by the load rules.

**Map**
- All routes drawn together; the selected route is coloured segment by segment by risk.
- Origin (A) and destination (B) markers, zoom controls and a mileage scale.
- Hover a checkpoint to see its weather, ETA and the reason for its risk level.
- Click a route to select it. Click a checkpoint, or its table row, to zoom to it.

**Weather heatmap**
- Risk heatmap along the corridor of all routes, for the 48 hours from departure.
- Hour slider with play and pause, and an on/off switch.
- Hover a heatmap area to see wind, rain and snow for the selected hour.

**Quality**
- Loading states, field-level validation, error messages with retry, and an error boundary.
- Responsive layout (the map moves below the planner on narrow screens).
- Labelled controls, keyboard support and reduced-motion support.

## Quick start with Docker

**Requirements:** Docker Desktop, or Docker Engine with Compose v2, and an internet connection. Nothing else needs to be installed.

From the project root:

```bash
docker compose up --build -d
```

Open **http://localhost:8000**. One container serves both the web app and the API. It listens only on your own machine.

| Task | Command |
|---|---|
| Check status (wait for `healthy`) | `docker compose ps` |
| Follow logs | `docker compose logs -f` |
| Stop and remove the container | `docker compose down` |
| Apply code or dependency changes | `docker compose up --build -d` |
| Apply `.env` changes | `docker compose up -d` |
| Use another port | `APP_PORT=8080 docker compose up --build -d` |

The first build downloads the base images and packages, so it takes longer than later builds. If it fails on a slow network, run the same command again; completed steps and downloads are cached.

### What the image does

1. A Node 24 stage installs the front-end packages, type-checks and builds the React app.
2. A Python 3.12 stage installs the back-end packages and copies in the code and the built app.
3. Gunicorn runs Django as an unprivileged user. WhiteNoise serves the web app from the same origin.
4. A health check calls `/api/health` every 30 seconds.

## Using the app

1. Type an **Origin** and a **Destination** and pick from the suggestions.
2. Set the **Departure** time, which is read in your browser's time zone.
3. Set the **Load weight** and, if you like, the **checkpoint spacing**.
4. Select **Find safest route**. Long trips can take a while because several routing and weather requests are made.
5. Read the recommendation, then compare routes on the **Routes** tab and inspect the **Checkpoints** tab.
6. Move the heatmap slider, or press play, to see how conditions change over 48 hours.

## Configuration

Everything has a default. To override one, copy `.env.example` to `.env`, edit it and run `docker compose up -d`. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` | `8000` | Port on your machine |
| `DJANGO_SECRET_KEY` | generated at container start | Django secret key |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hostnames the app answers to (loopback is always allowed) |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `WEB_CONCURRENCY` | `3` | Gunicorn worker processes |
| `TRUCK_TIME_FACTOR` | `1.15` | Truck duration = routing (car) duration × factor |
| `ROUTING_TIMEOUT` | `25` | Seconds per routing request |
| `WEATHER_TIMEOUT` | `25` | Seconds per weather request |
| `GEOCODING_TIMEOUT` | `8` | Seconds per place-search request |
| `THROTTLE_ANON` | `240/min` | Request limit per client for general endpoints |
| `THROTTLE_HEAVY` | `20/min` | Request limit per client for analyze and heatmap combined |
| `OSRM_URL` | `https://router.project-osrm.org` | Routing provider |
| `OPEN_METEO_URL` | `https://api.open-meteo.com` | Weather provider |
| `PHOTON_URL` | `https://photon.komoot.io` | Place-search provider |
| `UPSTREAM_USER_AGENT` | `weather-aware-truck-routing/1.0` | User agent sent to providers |

These are not passed through by `docker-compose.yml` and apply to hosting or development:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | off | Django debug mode, for local development only |
| `DJANGO_SSL_REDIRECT` | off | Redirect HTTP to HTTPS behind a TLS proxy |
| `CORS_ALLOWED_ORIGINS` | empty (the Vite dev server in debug mode) | Only needed if the front end is hosted on another origin |
| `PORT` | `8000` | Port inside the container; many hosts set it automatically |
| `FRONTEND_DIST` | `frontend/dist` | Location of the built web app |
| `VITE_API_BASE` | `/api` | API base URL, read when the front end is built |

## How it works

### Request flow

```
Browser ── POST /api/analyze ──> Django ──> OSRM          (route options)
                                       └──> Open-Meteo    (hourly weather per checkpoint)
Browser ── POST /api/heatmap ──> Django ──> Open-Meteo    (hourly weather per corridor cell)
Browser ── GET  /api/geocode ──> Django ──> Photon        (place search)
```

The heatmap is requested after the routes arrive, so a heatmap failure never blocks the results.

### Routes

OSRM often returns only one or two alternatives. Spotter also requests "via" routes through points offset 14% and 26% of the straight-line distance to either side of the midpoint. A candidate is kept only if it is no more than 1.6 times the length of the fastest route and overlaps each chosen route by less than 80%. If fewer than three distinct routes exist, the app says so.

Routes are lettered A, B, C in the order generated (A is the fastest the router found) and listed in recommendation order.

### Checkpoints and arrival times

- Checkpoints are placed at the origin, at the chosen spacing and at the destination.
- Automatic spacing: 10 mi for trips up to 200 mi, 25 mi up to 800 mi, otherwise 50 mi.
- Each route has at most 120 checkpoints; very long routes use wider spacing, and the app shows the spacing actually used.
- ETA = departure + truck duration × (checkpoint mile ÷ route miles).
- Weather is read from the forecast hour nearest the ETA. Missing forecast data is reported as unavailable and is never treated as calm.

### Risk rules

A checkpoint takes the worst of its wind, rain and snow levels.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25 to < 35 | 35 to < 45 | 45 to < 55 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | > 0.25–0.50 | > 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | > 1.0–2.0 | > 2.0–3.0 | > 3.0 |

Load rules, which can only raise a level:

| Wind | Load | Result |
|---|---|---|
| ≥ 55 mph | any | No Travel |
| 45 to < 55 mph | over 30,000 lb | No Travel |
| 35 to < 45 mph | over 40,000 lb | Severe |

The assessment brief's bands share edges (for example 0.10–0.25 and 0.25–0.50). Because it writes the top rain and snow bands as "greater than", Spotter includes each upper edge in the lower band: 0.25 in/hr of rain is Moderate. Boundary tests cover these cases.

### Recommendation

Each checkpoint represents the road from halfway to the previous checkpoint to halfway to the next, which gives miles at each risk level and a mileage-weighted average risk from 0 to 4. Routes are ordered by:

1. No Travel: a route with none always beats a route with any
2. Fewest No Travel miles
3. Fewest Severe miles
4. Fewest High miles
5. Lowest average risk
6. Shortest travel time

Before comparing, miles are rounded to the nearest 5, average risk to 0.1 and time to 1 minute. Values that round to the same step fall through to the next rule, so a stray mile of Severe weather on a long haul doesn't force a multi-hour detour. Exact values break any remaining tie. The constants are in `backend/trips/domain/recommend.py`.

Ranking No Travel above Severe is an addition to the brief's order of preference.

### Weather heatmap

- Points are placed about every 25 miles along each route and 18 miles to either side, with overlaps removed.
- The grid is limited to 180 cells. On long trips the spacing widens and each cell is drawn larger.
- Each cell has a risk level for hour 0 (departure, rounded down to the hour) through hour 48, including the load rules.
- Hours beyond the forecast range are left blank.
- All hours arrive in one response, so moving the slider makes no network requests.

### Performance

- Weather is fetched in batches, in parallel, and cached for 15 minutes per location (about 1 km).
- Place searches are debounced in the browser and cached on the server for 1 hour.
- Route lines are simplified to at most 1,500 points for display.
- The map library is built as a separate bundle so browsers can cache it.

## API reference

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness check, returns `{"status": "ok"}` |
| `GET /api/geocode?q=Chicago` | Place suggestions. Add `strict=1` to receive an error when nothing matches |
| `POST /api/analyze` | Routes, checkpoints, risk and recommendation |
| `POST /api/heatmap` | Hourly corridor risk grid |

### `POST /api/analyze`

```json
{
  "origin": { "label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298 },
  "destination": { "label": "Dallas, TX", "lat": 32.7767, "lon": -96.797 },
  "departure": "2026-12-01T08:00:00-06:00",
  "load_weight_lb": 38000,
  "interval_miles": 25
}
```

| Field | Rules |
|---|---|
| `origin`, `destination` | Label plus latitude and longitude; at least 0.5 mi apart |
| `departure` | ISO 8601 with a time-zone offset; no more than 2 hours in the past or 14 days ahead |
| `load_weight_lb` | 0 to 80,000 |
| `interval_miles` | Optional: 10, 25, 50 or `null` for automatic |

The trip must also end within the weather provider's forecast range (about 15 days).

The response contains:

- `request`: the inputs as understood
- `recommendation`: `route_id`, `route_name`, `reasons`, `travel_advised`
- `routes`: in rank order, each with geometry (polyline, precision 6), distance, duration, departure, arrival, `miles_by_level`, `avg_risk`, peak level, tags, summary and `checkpoints` (position, mile, ETA, weather, risk and its drivers)
- `meta`: data sources, generation time and the truck time factor

### `POST /api/heatmap`

```json
{
  "geometries": ["gd`{nAn}ncfD~o}~Bv{hzBvgneAfzo`@"],
  "departure": "2026-12-01T08:00:00-06:00",
  "load_weight_lb": 38000
}
```

Send one to three route geometries, as returned by `/api/analyze`. The response contains `start`, `hours` (48), `cell_radius_mi` and `cells`. Each cell has `lat`, `lon` and 49 hourly values in `levels`, `wind`, `rain` and `snow`. A level is 0 (Low) to 4 (No Travel), or -1 when there is no forecast.

## Error handling

Every API error uses one shape:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Please check the highlighted fields.", "details": {} } }
```

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Invalid input; `details.fields` names the problems |
| `PARSE_ERROR` | 400 | The request body isn't valid JSON |
| `PLACE_NOT_FOUND` | 404 | Strict place search found nothing |
| `NOT_FOUND` | 404 | Unknown API endpoint |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP method |
| `NO_ROUTE` | 422 | No drivable route |
| `FORECAST_OUT_OF_RANGE` | 422 | No weather forecast for part of the trip |
| `RATE_LIMITED` | 429 | Too many requests from this client |
| `INTERNAL_ERROR` | 500 | Unexpected error; details are logged, not returned |
| `UPSTREAM_ERROR` | 502 | A data provider failed or sent bad data |
| `UPSTREAM_RATE_LIMITED` | 503 | A data provider is limiting requests |
| `UPSTREAM_TIMEOUT` | 504 | A data provider took too long |

**Server:** bounded timeouts, retries with backoff for provider requests, input validation and request throttling.

**Browser:** request cancellation and timeouts, offline detection, messages beside the relevant field, retry buttons, a separate retry for the heatmap, and fallbacks if the map or the whole interface fails to load.

## Project structure

```
.
├── Dockerfile                 two-stage build: React app, then Django
├── docker-compose.yml         local run configuration
├── render.yaml                Render deployment blueprint
├── .env.example               optional settings
├── backend/
│   ├── manage.py
│   ├── requirements.txt       runtime packages
│   ├── requirements-dev.txt   test packages
│   ├── pytest.ini
│   ├── config/                settings, test settings, URLs, WSGI
│   └── trips/
│       ├── views.py           API endpoints
│       ├── serializers.py     request validation
│       ├── exceptions.py      typed errors and the error response format
│       ├── urls.py
│       ├── domain/            pure logic
│       │   ├── risk.py        thresholds and load rules
│       │   ├── recommend.py   scoring, ranking and reasons
│       │   └── geo.py         distances, polylines, sampling, simplification
│       ├── services/
│       │   ├── analysis.py    builds the analyze and heatmap responses
│       │   ├── routing.py     OSRM and extra route candidates
│       │   ├── weather.py     Open-Meteo, batching and caching
│       │   ├── geocoding.py   Photon place search
│       │   └── http.py        timeouts, retries and error mapping
│       └── tests/
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── public/                favicon
    └── src/
        ├── main.tsx
        ├── App.tsx            page layout and request flow
        ├── api.ts             API client
        ├── types.ts
        ├── env.d.ts
        ├── styles.css
        ├── components/        TripForm, PlaceInput, Recommendation, RouteCard,
        │                      CheckpointTable, MapView, HeatmapControl,
        │                      RiskBits, Icons, ErrorBoundary
        └── lib/               formatting, polylines, risk colours, validation
```

## Local development without Docker

**Requirements:** Python 3.12 and Node.js 20 or newer.

Terminal 1, the API on http://127.0.0.1:8000:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
DJANGO_DEBUG=1 python manage.py runserver
```

Terminal 2, the web app on http://localhost:5173 with hot reload (it forwards `/api` to Django):

```bash
cd frontend
npm install
npm run dev
```

Django reads settings from environment variables; it doesn't load `.env` on its own.

### Tests and checks

The tests run on your machine; they aren't included in the Docker image.

```bash
cd backend && source .venv/bin/activate && pytest
```

```bash
cd frontend && npm test && npm run typecheck
```

Back-end tests cover the risk boundaries, load rules, ranking, geometry, orchestration and API errors, with providers replaced by test doubles. Front-end tests cover form validation and polyline decoding.

## Deployment

The Docker image runs on any host that supports containers.

### Render

1. Push the project to a GitHub repository.
2. In Render, choose **New**, then **Blueprint**, and select the repository.
3. Render reads `render.yaml`, which builds the image, generates the secret key, allows `.onrender.com` hostnames, turns on the HTTPS redirect and uses `/api/health` as the health check.

On free hosting plans, the first request after a period of inactivity can be slow.

### Other hosts

Set `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`, and set `DJANGO_SSL_REDIRECT=1` if TLS ends at a proxy. The app listens on `PORT`.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `port is already allocated` | Stop whatever uses port 8000, or run with `APP_PORT=8080` |
| `Cannot connect to the Docker daemon` | Start Docker Desktop |
| Build times out | Run `docker compose up --build -d` again |
| Container isn't `healthy` | Check `docker compose logs -f` |
| Request timed out | The providers or your network are slow; retry, or raise the timeout settings |
| Too many requests | Wait a minute and try again |
| Map stays on "Loading map" | The base map comes from `basemaps.cartocdn.com`; check your connection and that it isn't blocked |
| Fewer than three routes | No other sufficiently different road route exists |
| Forecast unavailable | Choose an earlier departure |

## Assumptions and limitations

- **Car routing:** OSRM's public service routes cars. It ignores truck height, weight and hazardous-material restrictions, so verify routes before driving them.
- **Travel time:** durations are scaled by a fixed factor. Rest breaks, hours-of-service rules and traffic aren't modelled.
- **Weather:** wind is sustained speed at 10 m, not gusts. Rain and snowfall are hourly totals, treated as inches per hour. Forecasts come from gridded models, not road sensors.
- **Providers:** the default services are free public endpoints intended for light use and without uptime guarantees. For production, point the provider URLs at self-hosted or commercial services.
- **Caching:** each server process has its own in-memory cache and request counters, so limits apply per process.
- **Time zones:** times are shown in the browser's time zone, not the local time along the route.

## Data and attribution

- Routing: [OSRM](https://project-osrm.org/), using [OpenStreetMap](https://www.openstreetmap.org/copyright) data
- Place search: [Photon](https://photon.komoot.io/), using OpenStreetMap data
- Weather: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0; the free service is for non-commercial use)
- Base map: [CARTO](https://carto.com/attributions) and OpenStreetMap contributors
- Font: Inter, from Google Fonts

Check each provider's terms before using the app commercially.

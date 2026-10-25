# Frontend: ResiliNet · Boston hospital cascade

A SvelteKit site over two models. A thin FastAPI app (`api/`) runs them; the
site (`web/`) draws them. Minimal dark theme, no account, no database.

- **Weekly** (the default): the ResiliNet nine-block pipeline in `pipeline/`,
  through `pipeline.api`, the same facade the Streamlit app and the tests use.
  Real Suffolk County census tracts and hospitals, a simulated epidemic.
- **Daily**: the earlier, more detailed daily cascade model in `seir/`, under
  `/daily`.

## Run it

Python 3.11+ and Node 20+. From the repository root:

```bash
# once
pip install -r requirements.txt -r seir/requirements.txt -r frontend/api/requirements.txt
npm --prefix frontend/web install

# terminal 1: the model API on :8000
uvicorn main:app --app-dir frontend/api --port 8000

# terminal 2: the site on :5173 (proxies /api to :8000)
npm --prefix frontend/web run dev
```

Open http://localhost:5173.

For a demo from one process, build the site once; the API then serves it too:

```bash
npm --prefix frontend/web run build
uvicorn main:app --app-dir frontend/api --port 8000      # open http://localhost:8000
```

The first visit to "Tested on real data" runs `scripts/run_backtest.py` once
(about 20 seconds) and saves `artifacts/evaluation.json`; later visits read it.

The map basemap (CARTO dark tiles) needs internet and, to drop CARTO's "API key
required" watermark, a free key from https://carto.com/basemaps/apikey/ in
`frontend/web/.env` (see `.env.example`; git ignores `.env`). The key is read at
build time, so rebuild after setting it. Offline, the maps still draw tracts,
neighborhoods and hospitals on a plain dark background.

## Weekly pages

| page | what it shows |
|---|---|
| Map | the 230 Suffolk census tracts coloured by access score on one fixed 0 to 100 scale, hospitals as circles sized by beds and coloured by score; the four headline numbers (hospitals over capacity, people who can't get a bed, people sent elsewhere, tracts with poor access) against the no-events run; click a tract for where its patients go |
| Hospitals | patients wanting a bed against beds for every hospital, one hospital in detail, beds and scores week by week, and the full table |
| Census tracts | every tract, searchable and sortable; one tract's catchment (distance, share, hospital score, ceiling) and its access and unmet need over time |
| Scenario lab | add closures and bed cuts; **What would help** (fixes tried on your scenario, ranked, with Apply); the week with and without your events, before and after rerouting, the hardest-hit tracts, hospital changes and the reroute ledger |
| Tested on real data | the fixed-origin and rolling-origin backtests against HHS Suffolk hospital data, next to "next week = this week"; the model loses and the page says so |
| Data and downloads | the data mode, the hospital crosswalk and exclusions, tract counts, loader notes, the raw manifest and the four exports (`hospital_week.csv`, `district_week.csv`, `reroute_week.csv`, `run.json`) |
| How it works | the four weekly steps, this run's epidemic, units, limits and the equations |

"What if…?" (top right) holds the dataset (real, synthetic, 3-tract test
fixture), events, R₀ and p_H; "More settings" has the starting infections,
weeks, distance decay d₀, α_D, α_H and the nearest-hospital fallback. Defaults
and ranges match the Streamlit app. The bar at the bottom picks the week (space
plays, arrow keys step) and the before/after rerouting view.

## Daily pages (`/daily`)

| page | what it shows |
|---|---|
| Map | Boston's 15 neighborhoods coloured by residents in hospital, sick now, ever infected or hospital care lost, on one scale for the whole run; hospitals by how full they are; click a neighborhood for its numbers and where its patients go; day-by-day playback |
| Spread | people infected and in hospital over time, neighborhood by neighborhood, and by age; R₀, Rₑff, rates and force of infection under "Technical detail" |
| Hospitals | how full each hospital is day by day, one hospital in detail, who loses their usual hospital; the FDNA dependency graph, operability, rerouting and criticality under "What makes a hospital fail" |
| Range of outcomes | many stochastic runs of the same outbreak (what luck can do) and which assumptions move the result most |
| Tested on real data | the Omicron fit and the never-fitted winter 2020–21 checks against HHS and CTP data, next to a "same as last week" baseline; sliders to try to break the fit |
| How it works | the daily steps in plain words, the current scenario, assumptions and sources; equations folded away |

Its "What if…?" panel shows five basic settings: disease, how contagious, how
severe, already immune and when a hospital counts as full. "More settings"
holds the rest: latent and infectious periods, lengths of stay, seed size and
run length, hospitals that stay open, distance decay, staff absence, ICU strain
and FDNA disruptions (cap a node for a window of days). Space plays the
timeline; arrow keys step a day (shift: a week).

## API

All JSON. The weekly routes are in `api/resilinet.py`, the daily ones in
`api/main.py` (changes are dotted paths, as with the CLI's `--set`).

| endpoint | does |
|---|---|
| `GET /api/rn/meta` | datasets, slider defaults and ranges, threshold, event kinds |
| `GET /api/rn/geo/{dataset}` | tract outlines; feature `id` is the tract's index in the run's `districts` |
| `POST /api/rn/run` | `{dataset, r0, p_h, seed, d0, alpha_d, alpha_h, weeks, fallback, events}` → hospitals, tracts with names and catchments, the weekly epidemic, and every week before and after rerouting, for the scenario and (with events) the no-events baseline; engine errors come back as 422 with the engine's message |
| `POST /api/rn/export/{file}` | the same body → `hospital_week.csv`, `district_week.csv`, `reroute_week.csv` or `run.json` from `pipeline.api` |
| `POST /api/rn/mitigate` | the same body → fixes tried on that scenario (25% more beds at up to 4 hospitals, R0 × 0.9 and × 0.8, shorter or cancelled closures, restored beds), each a full rerun, ranked by people who get a bed over the run, with tract-weeks of poor access fixed and how to apply each one |
| `GET /api/rn/evaluation` | `artifacts/evaluation.json` (computed once if missing) plus facility names |
| `GET /api/scenarios`, `GET /api/scenario/{id}` | scenario list; one scenario's config, derived rates and map places |
| `GET /api/presets` | disease presets and their sources |
| `POST /api/run` | `{scenario, epi, system, events}` → SEIR curves, rates, by-neighborhood and by-age series, and for system scenarios hospital load, operability, diversion, access |
| `POST /api/ensemble` | `+ {runs, seed}` → quantile bands, sample runs, peaks, take-off share |
| `POST /api/sensitivity` | `+ {params, metric, rel}` → one-at-a-time table |
| `POST /api/criticality` | `+ {level}` → FDNA nodes ranked by extra weighted access loss |
| `POST /api/validation` | `{omicron, winter}` changes → model, observed and naive series with scores |

`pytest frontend/api` runs the API's smoke tests (both models).

## Where the model pieces come from

- `pipeline/`, `validation/`, `data/raw/`: the ResiliNet weekly pipeline,
  its backtest and its committed real data, unchanged by the site. Tract names
  on the site come from the MassGIS tract file plus the neighborhood outlines
  below; Chelsea, Revere and Winthrop by tract number.

- `seir/cascade/epi`: the SEIR layer, unchanged.
- `seir/cascade/{allocation,network,fdna,reroute,equity,recorder,scenario,api,contracts}.py`:
  the cascade reference's system layer, copied unchanged, with its tests in
  `seir/tests/test_system.py` (scenarios in `seir/systems/`).
- `seir/systems/boston_city.yaml`: a 15-neighborhood, 7-hospital Boston scenario
  generated by `seir/systems/make_boston.py` from two CSV tables. Populations,
  coordinates, the Boston share of beds, travel times and vulnerability weights
  are approximate and labelled as assumptions on the How it works page.
- `seir/systems/boston_districts.geojson`: the map's neighborhood outlines,
  merged from the City of Boston's 26 neighborhood boundaries by
  `seir/systems/make_districts.py` (needs `shapely`; not needed to run the site).

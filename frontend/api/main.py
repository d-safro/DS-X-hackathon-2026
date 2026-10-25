"""Thin HTTP layer over the models for the SvelteKit frontend.

/api/rn/* serves the ResiliNet weekly pipeline (pipeline/, see resilinet.py);
the other endpoints serve the daily cascade model in seir/.

    uvicorn main:app --app-dir frontend/api --reload --port 8000

With frontend/web/build present (npm run build), the same server also serves
the site at http://127.0.0.1:8000.

Nothing here models anything: it loads scenarios, applies the changes the
page asks for (dotted paths, as with the CLI's --set), calls cascade.api /
cascade.epi and turns xarray results into plain JSON arrays.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import sys
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

ROOT = Path(__file__).resolve().parents[2] / "seir"
sys.path.insert(0, str(ROOT))

from cascade import api as system_api  # noqa: E402
from cascade.epi import DISEASES, ScenarioConfig, SEIREngine, SEIRResult, data  # noqa: E402
from cascade.epi.calibrate import aligned  # noqa: E402
from cascade.epi.ensemble import bands, run_ensemble, takeoff_share  # noqa: E402
from cascade.epi.presets import SOURCES  # noqa: E402
from cascade.epi.sensitivity import one_at_a_time  # noqa: E402
from cascade.epi.validation import score, validate_series  # noqa: E402
from cascade.fdna import Event  # noqa: E402
from cascade.scenario import SystemConfig, build  # noqa: E402

SCENARIOS: dict[str, dict] = {
    "boston_city": {
        "kind": "system",
        "path": ROOT / "systems" / "boston_city.yaml",
        "title": "Boston · 15 neighborhoods",
        "blurb": (
            "Omicron-like wave across Boston neighborhoods and 7 acute hospitals. Illustrative."
        ),
    },
    "boston_demo": {
        "kind": "system",
        "path": ROOT / "systems" / "boston_demo.yaml",
        "title": "Reference demo · 3 neighborhoods",
        "blurb": "The cascade reference: Dorchester, Roxbury, Back Bay and 4 hospitals.",
    },
    "omicron_2021": {
        "kind": "epi",
        "path": ROOT / "scenarios" / "omicron_2021.yaml",
        "title": "Omicron 2021 · Massachusetts",
        "blurb": "Calibrated to HHS admissions, Dec 2021 – Mar 2022.",
    },
    "winter_2020": {
        "kind": "epi",
        "path": ROOT / "scenarios" / "winter_2020.yaml",
        "title": "Winter 2020 · Massachusetts",
        "blurb": "Ancestral strain, fitted to admissions.",
    },
    "omicron_2021_mobility": {
        "kind": "epi",
        "path": ROOT / "scenarios" / "omicron_2021_mobility.yaml",
        "title": "Omicron · mobility-driven",
        "blurb": "Transmission follows Google mobility.",
    },
    "novel_flu": {
        "kind": "epi",
        "path": ROOT / "scenarios" / "novel_flu.yaml",
        "title": "Novel influenza",
        "blurb": "Pandemic-flu what-if.",
    },
    "example_3patch": {
        "kind": "epi",
        "path": ROOT / "scenarios" / "example_3patch.yaml",
        "title": "Three neighborhoods",
        "blurb": "Illustrative 3-patch example.",
    },
}
ALIASES = {"Back Bay": "Back Bay-Beacon Hill"}  # older scenarios' patch names -> table rows

# Ensembles use worker processes. Forking a threaded server can deadlock, so start
# workers from a clean server process instead (macOS and Windows already spawn).
if "forkserver" in multiprocessing.get_all_start_methods():
    multiprocessing.set_start_method("forkserver", force=True)

app = FastAPI(title="Outbreak cascade API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2048)


# ---- requests ------------------------------------------------------------------
class Changes(BaseModel):
    scenario: str = "boston_city"
    epi: dict[str, Any] = {}  # dotted paths into the SEIR scenario, e.g. {"disease.r0": 2.2}
    system: dict[
        str, Any
    ] = {}  # dotted paths into the system config, e.g. {"rerouting.occ_on": 0.9}
    events: list[Event] | None = None


class EnsembleRequest(Changes):
    runs: int = Field(default=40, ge=2, le=200)
    seed: int = 0


class SensitivityRequest(Changes):
    params: list[str] = [
        "disease.r0",
        "disease.infectious_period",
        "disease.latent_period",
        "disease.hosp_scale",
        "disease.los_ward",
        "disease.los_icu",
    ]
    metric: str = "peak_inpatients"
    rel: float = Field(default=0.25, gt=0, lt=1)


class CriticalityRequest(Changes):
    level: float = Field(default=0.0, ge=0, le=100)


class ValidationRequest(BaseModel):
    omicron: dict[str, Any] = {}
    winter: dict[str, Any] = {}


# ---- helpers -------------------------------------------------------------------
def _clean(x):
    """JSON-safe: numpy -> python, NaN/inf -> None, floats rounded."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if not math.isfinite(x):
            return None
        return round(x, 6) if abs(x) < 1 else round(x, 3)
    if isinstance(x, (pd.Timestamp,)):
        return str(x.date())
    return x


def _spec(name: str) -> dict:
    if name not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario {name!r}")
    return SCENARIOS[name]


@cache
def _base(name: str):
    spec = _spec(name)
    return (
        system_api.load(spec["path"])
        if spec["kind"] == "system"
        else ScenarioConfig.from_yaml(spec["path"])
    )


def _set(data: dict, path: str, value) -> None:
    node, keys = data, path.split(".")
    for key in keys[:-1]:
        if not isinstance(node.get(key), dict):
            raise KeyError(f"{path}: {key!r} is not a section")
        node = node[key]
    node[keys[-1]] = value


def _configure(req: Changes):
    """(system config or None, epi config) with the request's changes applied."""
    base = _base(req.scenario)
    try:
        if isinstance(base, SystemConfig):
            epi = base.epi.updated(req.epi) if req.epi else base.epi
            d = base.model_dump()
            d["epi"] = epi.model_dump()
            for k, v in req.system.items():
                _set(d, k, v)
            if req.events is not None:
                d["events"] = [e.model_dump() for e in req.events]
            cfg = SystemConfig.model_validate(d)
            return cfg, cfg.epi
        return None, base.updated(req.epi) if req.epi else base
    except (ValidationError, KeyError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


@lru_cache(maxsize=1)
def _places() -> tuple[pd.DataFrame, pd.DataFrame]:
    nb = pd.read_csv(ROOT / "systems" / "boston_neighborhoods.csv").set_index("patch")
    hosp = pd.read_csv(ROOT / "systems" / "boston_hospitals.csv").set_index("id")
    return nb, hosp


@lru_cache(maxsize=1)
def _districts() -> dict[str, dict]:
    """Neighborhood outlines by patch name (systems/make_districts.py), if present."""
    path = ROOT / "systems" / "boston_districts.geojson"
    if not path.exists():
        return {}
    return {f["properties"]["patch"]: f for f in json.loads(path.read_text())["features"]}


def _geo(epi: ScenarioConfig, sys_cfg: SystemConfig | None) -> dict:
    nb, hosp = _places()
    outlines = _districts()
    patches, districts = [], []
    for p, n in zip(epi.population.patches, epi.population.N.sum(axis=1), strict=True):
        row = nb.loc[ALIASES.get(p, p)] if ALIASES.get(p, p) in nb.index else None
        outline = outlines.get(ALIASES.get(p, p))
        vuln = sys_cfg.equity.vulnerability.get(p, 1.0) if sys_cfg else 1.0
        patches.append(
            {
                "id": p,
                "population": float(n),
                "vulnerability": vuln,
                "lat": None if row is None else float(row.lat),
                "lon": None if row is None else float(row.lon),
                "label": outline["properties"]["label"] if outline else None,
            }
        )
        if outline:
            districts.append(
                {
                    "type": "Feature",
                    "id": len(patches) - 1,
                    "properties": {"patch": p},
                    "geometry": outline["geometry"],
                }
            )
    hospitals = []
    if sys_cfg:
        for h in sys_cfg.network.hospitals:
            row = hosp.loc[h.id] if h.id in hosp.index else None
            hospitals.append(
                {
                    "id": h.id,
                    "name": h.name or (row["name"] if row is not None else h.id),
                    "ward_beds": h.ward_beds,
                    "icu_beds": h.icu_beds,
                    "er": h.er,
                    "baseline_occupancy": h.baseline_occupancy,
                    "lat": None if row is None else float(row.lat),
                    "lon": None if row is None else float(row.lon),
                }
            )
    mappable = all(p["lat"] is not None for p in patches)
    return {
        "patches": patches,
        "hospitals": hospitals,
        "mappable": mappable,
        "districts": {"type": "FeatureCollection", "features": districts} if districts else None,
    }


def _describe(epi: ScenarioConfig) -> dict:
    return SEIREngine.from_config(epi).describe(seeding=epi.seeding)


def _epi_payload(res: SEIRResult) -> dict:
    ds = res.ds
    pop = res.population.sum("age")
    w = res.population / res.population.sum()

    def city(da):
        return da.sum(["patch", "age"]).values

    def rate(name):
        if name not in ds:
            return None
        da = ds[name]
        return (da * w).sum(["patch", "age"]).values if "age" in da.dims else da.values

    comps = {c: city(ds[c]) for c in res.structure.compartments}
    infections = res.infections().sum("age")  # [time, patch]
    infectious = sum(ds[c] for c in res.structure.infectious).sum("age")
    has_h = "H" in ds and "C" in ds
    by_patch = {
        "infections": infections.values,
        "infectious": infectious.values,
        "prevalence": (infectious / pop).values,
        "attack_rate": (infections.cumsum("time") / pop).values,
    }
    if has_h:
        by_patch["inpatients"] = res.inpatients().values
        by_patch["new_hosp"] = ds["new_hosp"].sum("age").values
    if "force_of_infection" in ds and "age" in ds["force_of_infection"].dims:
        wp = res.population / pop
        by_patch["force_of_infection"] = (ds["force_of_infection"] * wp).sum("age").values
    citywide = {
        **comps,
        "infections": infections.sum("patch").values,
        "infectious": infectious.sum("patch").values,
    }
    for flow in ("new_hosp", "new_icu", "new_deaths"):
        if flow in ds:
            citywide[flow] = city(ds[flow])
    if has_h:
        citywide["inpatients"] = res.inpatients().sum("patch").values
    by_age = {
        "infections": res.infections().sum("patch").values.T,
        "attack_rate": (
            res.infections().sum(["patch", "time"]) / res.population.sum("patch")
        ).values,
    }
    if "new_hosp" in ds:
        by_age["new_hosp"] = ds["new_hosp"].sum("patch").values.T
    return {
        "dates": [str(t)[:10] for t in ds.time.values],
        "compartments": list(res.structure.compartments),
        "ages": list(ds.age.values),
        "summary": res.summary(),
        "citywide": citywide,
        "rates": {
            k: rate(k)
            for k in (
                "transmission_rate",
                "incubation_rate",
                "recovery_rate",
                "force_of_infection",
                "r_eff",
            )
        },
        "observed_rates": {k: v.values for k, v in res.observed_rates().items()},
        "by_patch": by_patch,
        "by_age": by_age,
    }


# ---- endpoints -----------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/scenarios")
def scenarios():
    return [
        {"id": k, "kind": v["kind"], "title": v["title"], "blurb": v["blurb"]}
        for k, v in SCENARIOS.items()
    ]


@app.get("/api/presets")
def presets():
    return _clean({"diseases": DISEASES, "sources": SOURCES})


@app.get("/api/scenario/{name}")
def scenario(name: str):
    base = _base(name)
    sys_cfg = base if isinstance(base, SystemConfig) else None
    epi = sys_cfg.epi if sys_cfg else base
    out = {
        "id": name,
        **{k: v for k, v in _spec(name).items() if k != "path"},
        "epi": epi.model_dump(mode="json"),
        "describe": _describe(epi),
        "geo": _geo(epi, sys_cfg),
    }
    if sys_cfg:
        out["system"] = sys_cfg.model_dump(mode="json", exclude={"epi"})
    return _clean(out)


@app.post("/api/describe")
def describe(req: Changes):
    _, epi = _configure(req)
    return _clean(_describe(epi))


@app.post("/api/run")
def run(req: Changes):
    sys_cfg, epi = _configure(req)
    out: dict = {"scenario": req.scenario, "describe": _describe(epi), "geo": _geo(epi, sys_cfg)}
    if sys_cfg is None:
        res = SEIREngine.from_config(epi).run(epi.seeding, epi.sim.days)
        out["epi"] = _epi_payload(res)
        out["system"] = None
        return _clean(out)

    try:
        sim, seir, recorder = build(sys_cfg)
    except ValueError as e:  # e.g. an event naming an unknown node
        raise HTTPException(422, str(e)) from e
    sim.run(epi.sim.days)
    res = SEIRResult.from_records(
        seir.records, seir.engine.initial_state(epi.seeding), seir.engine.structure, epi.population
    )
    s = recorder.to_dataset()
    graph = sim.module("fdna").graph.graph
    summary = system_api.RunResult(system=s, epi=res).summary()
    out["epi"] = _epi_payload(res)
    out["system"] = {
        "summary": summary,
        "hospitals": list(s.hospital.values),
        "nodes": list(s.node.values),
        "edges": [
            {"src": a, "dst": b, "sod": d["sod"], "cod": d["cod"]}
            for a, b, d in graph.edges(data=True)
        ],
        "shares": sim.module("allocation").shares,
        "travel": np.asarray(sys_cfg.network.travel_minutes),
        **{
            k: s[k].values
            for k in (
                "occupancy_ward",
                "occupancy_icu",
                "operability",
                "on_diversion",
                "access",
                "lost_person_days",
                "weighted_loss",
                "diverted_patients",
                "overflow",
                "node_operability",
            )
        },
        "arrivals": s["arrivals"].values,
    }
    return _clean(out)


@app.post("/api/ensemble")
def ensemble(req: EnsembleRequest):
    _, epi = _configure(req)
    ens = run_ensemble(
        epi,
        runs=req.runs,
        seed=req.seed,
        workers=min(int(os.environ.get("MAX_WORKERS", 4)), os.cpu_count() or 1),
    )
    q = bands(ens, q=(0.05, 0.25, 0.5, 0.75, 0.95))
    out = {
        "dates": [str(t)[:10] for t in ens.time.values],
        "runs": req.runs,
        "quantiles": [0.05, 0.25, 0.5, 0.75, 0.95],
        "takeoff_share": takeoff_share(ens),
        "bands": {},
        "samples": {},
        "peaks": {},
    }
    city = ens.sum("patch")
    for v in q.data_vars:
        out["bands"][v] = q[v].transpose("quantile", "time").values
        if "run" in city[v].dims:
            out["samples"][v] = city[v].isel(run=slice(0, 12)).values
            if v != "r_eff":
                out["peaks"][v] = city[v].max("time").values
    return _clean(out)


@app.post("/api/sensitivity")
def sensitivity(req: SensitivityRequest):
    _, epi = _configure(req)
    try:
        df = one_at_a_time(epi, req.params, metric=req.metric, rel=req.rel)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    return _clean({"metric": req.metric, "rel": req.rel, "rows": df.to_dict(orient="records")})


@app.post("/api/criticality")
def criticality(req: CriticalityRequest):
    sys_cfg, _ = _configure(req)
    if sys_cfg is None:
        raise HTTPException(422, "criticality needs a system scenario (hospitals and FDNA)")
    try:
        df = system_api.criticality(sys_cfg, level=req.level)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _clean({"level": req.level, "rows": df.to_dict(orient="records")})


def _weekly_check(
    cfg: ScenarioConfig, observed: pd.Series, variable: str, how: str, label: str
) -> dict:
    res = SEIREngine.from_config(cfg).run(cfg.seeding, cfg.sim.days)
    model = pd.Series(
        aligned(res.series(variable), observed.index, 7, "end", how), index=observed.index
    )
    naive = observed.shift(1)  # last week's value, carried forward
    report = validate_series(model, observed)
    return {
        "label": label,
        "weeks": [str(d.date()) for d in observed.index],
        "observed": observed.values,
        "model": model.values,
        "naive": naive.values,
        "checks": report.to_dict(),
        "passed": report.passed,
        "score": score(model, observed),
        "naive_score": score(naive.dropna(), observed[naive.notna()]),
        "params": {"r0": cfg.disease.r0, "hosp_scale": cfg.disease.hosp_scale},
    }


@app.post("/api/validation")
def validation(req: ValidationRequest):
    try:
        adm = data.weekly(data.hhs_state_admissions(ROOT / "data" / "hhs_ma_daily_admissions.csv"))
        omicron = (
            _base("omicron_2021").updated(req.omicron) if req.omicron else _base("omicron_2021")
        )
        winter = _base("winter_2020").updated(req.winter) if req.winter else _base("winter_2020")
        census = (
            data.ctp_state(ROOT / "data" / "ctp_ma_hospital_census.csv").resample("W-SAT").mean()
        )
        return _clean(
            {
                "omicron": _weekly_check(
                    omicron,
                    adm["2021-12-25":"2022-03-05"],
                    "new_hosp",
                    "sum",
                    "Omicron · weekly COVID admissions (HHS)",
                ),
                "winter_icu": _weekly_check(
                    winter,
                    census.loc["2020-10-03":"2021-03-06", "inIcuCurrently"],
                    "icu",
                    "mean",
                    "Winter 2020–21 · ICU census (CTP, never fitted)",
                ),
                "winter_inpatients": _weekly_check(
                    winter,
                    census.loc["2020-10-03":"2021-03-06", "hospitalizedCurrently"],
                    "inpatients",
                    "mean",
                    "Winter 2020–21 · all COVID inpatients (CTP, never fitted)",
                ),
            }
        )
    except (ValidationError, KeyError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


# ---- the ResiliNet weekly pipeline (repo root pipeline/) --------------------------
from resilinet import router as resilinet_router  # noqa: E402

app.include_router(resilinet_router)


# ---- the built site (single-page app) --------------------------------------------
class _SPA(StaticFiles):
    """Static files with index.html for client-side routes such as /hospitals."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or path.startswith("api"):
                raise
            return await super().get_response("index.html", scope)


BUILD = Path(__file__).resolve().parents[1] / "web" / "build"
if BUILD.exists():
    app.mount("/", _SPA(directory=BUILD, html=True), name="site")

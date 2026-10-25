"""Smoke tests for the HTTP layer: every endpoint answers with the shapes the site reads.

pytest frontend/api
"""

import pytest
from fastapi.testclient import TestClient
from main import SCENARIOS, app

client = TestClient(app)


def post(path, body):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_scenarios_and_details():
    ids = {s["id"] for s in client.get("/api/scenarios").json()}
    assert ids == set(SCENARIOS)
    for sid in ids:
        r = client.get(f"/api/scenario/{sid}")
        assert r.status_code == 200, r.text
        assert r.json()["describe"]["r0"] > 0
    assert client.get("/api/scenario/nope").status_code == 404


def test_presets():
    p = client.get("/api/presets").json()
    assert "covid_omicron" in p["diseases"] and p["sources"]


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_every_scenario_runs(sid):
    r = post("/api/run", {"scenario": sid})
    days = len(r["epi"]["dates"])
    assert days > 0 and len(r["epi"]["citywide"]["S"]) == days
    assert len(r["epi"]["rates"]["r_eff"]) == days
    if SCENARIOS[sid]["kind"] == "system":
        s = r["system"]
        assert len(s["occupancy_ward"]) == days and len(s["occupancy_ward"][0]) == len(
            s["hospitals"]
        )
        assert len(s["access"][0]) == len(r["geo"]["patches"])
        assert r["geo"]["mappable"]
        assert len(r["geo"]["districts"]["features"]) == len(r["geo"]["patches"])
    else:
        assert r["system"] is None


def test_changes_apply():
    base = post("/api/run", {"scenario": "boston_city"})
    hot = post(
        "/api/run",
        {
            "scenario": "boston_city",
            "epi": {"disease.r0": 2.6, "sim.days": 90},
            "system": {"rerouting.occ_on": 0.9},
            "events": [{"node": "MGH.staff", "value": 20, "start": 10, "end": 50}],
        },
    )
    assert len(hot["epi"]["dates"]) == 90
    assert hot["epi"]["summary"]["attack_rate"] > base["epi"]["summary"]["attack_rate"]
    assert (
        hot["system"]["summary"]["hospital_days_on_diversion"]
        > base["system"]["summary"]["hospital_days_on_diversion"]
    )


def test_bad_changes_are_422():
    assert (
        client.post(
            "/api/run", json={"scenario": "boston_city", "epi": {"disease.r0": -1}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/run",
            json={"scenario": "boston_city", "events": [{"node": "nowhere", "value": 0}]},
        ).status_code
        == 422
    )


def test_ensemble_sensitivity_criticality_validation():
    e = post("/api/ensemble", {"scenario": "example_3patch", "runs": 4})
    assert len(e["bands"]["inpatients"]) == 5 and 0 <= e["takeoff_share"] <= 1
    s = post("/api/sensitivity", {"scenario": "example_3patch", "params": ["disease.r0"]})
    assert s["rows"][0]["metric_high"] > s["rows"][0]["metric_low"]
    c = post("/api/criticality", {"scenario": "boston_demo"})
    assert c["rows"] and "extra_loss" in c["rows"][0]
    v = post("/api/validation", {})
    assert v["omicron"]["passed"] and v["winter_icu"]["passed"]


# ---- ResiliNet weekly pipeline (/api/rn) -------------------------------------------
def test_rn_meta_lists_datasets_and_defaults():
    m = client.get("/api/rn/meta").json()
    assert {"synthetic", "golden"} <= {d["id"] for d in m["datasets"]}
    assert m["params"]["r0"]["default"] == 2.6 and m["threshold"] == 70


@pytest.mark.parametrize("dataset", ["synthetic", "golden", "real"])
def test_rn_run_and_geo_line_up(dataset):
    r = post("/api/rn/run", {"dataset": dataset, "weeks": 4})
    n = len(r["districts"])
    assert r["weeks"] == len(r["scenario"]) == 4 and r["baseline"] is None
    week = r["scenario"][2]
    for phase in ("before", "after"):
        assert len(week[phase]["access"]) == len(week[phase]["unmet"]) == n
        assert {h["id"] for h in week[phase]["hospitals"]} == {h["id"] for h in r["hospitals"]}
    g = client.get(f"/api/rn/geo/{dataset}").json()
    assert [f["properties"]["district_id"] for f in g["features"]] == [
        d["id"] for d in r["districts"]
    ]
    if dataset == "real":
        assert r["fallback_districts"] == ["25025170502"]
        assert all(d["area"] for d in r["districts"])


def test_rn_closing_a_hospital_adds_a_baseline_and_inherited_deficit():
    event = {"id": "e1", "kind": "close_hospital", "hospital_id": "SH0", "start_week": 1}
    r = post("/api/rn/run", {"dataset": "synthetic", "events": [event]})
    assert r["baseline"] is not None and r["run_id"] != r["base_run_id"]
    sh0 = next(h for h in r["scenario"][2]["after"]["hospitals"] if h["id"] == "SH0")
    assert sh0["closed"] and sh0["capacity"] == 0
    assert r["scenario"][2]["after"]["events"] == ["e1"]
    assert r["scenario"][0]["after"]["events"] == []


def test_rn_bad_input_is_422_with_the_engine_message():
    bad = {"id": "e1", "kind": "close_hospital", "hospital_id": "NOPE", "start_week": 0}
    r = client.post("/api/rn/run", json={"dataset": "synthetic", "events": [bad]})
    assert r.status_code == 422 and "NOPE" in r.json()["detail"]
    r = client.post("/api/rn/run", json={"dataset": "real", "fallback": False})
    assert r.status_code == 422 and "25025170502" in r.json()["detail"]


def test_rn_exports():
    body = {"dataset": "golden"}
    for name in ("hospital_week.csv", "district_week.csv", "reroute_week.csv"):
        r = client.post(f"/api/rn/export/{name}", json=body)
        assert r.status_code == 200 and r.text.startswith("# run_id=")
    r = client.post("/api/rn/export/run.json", json=body)
    assert r.status_code == 200 and r.json()["data_mode"] == "synthetic_demo"
    assert client.post("/api/rn/export/nope.csv", json=body).status_code == 404


def test_rn_evaluation_reads_the_artifact(tmp_path, monkeypatch):
    import resilinet

    fake = tmp_path / "evaluation.json"
    fake.write_text('{"status": "verified", "fixed_origin": {"forecast_pairs": 1}}')
    monkeypatch.setattr(resilinet, "EVALUATION", fake)
    e = client.get("/api/rn/evaluation").json()
    assert e["status"] == "verified"
    assert e["facilities"]["220086"]["hospitals"] == ["BIDMC_E", "BIDMC_W"]


def test_rn_mitigate_ranks_fixes_for_a_closure():
    body = {
        "dataset": "golden",
        "r0": 3.5,
        "events": [{"id": "e1", "kind": "close_hospital", "hospital_id": "H1", "start_week": 1}],
    }
    r = client.post("/api/rn/mitigate", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] in ("ok", "none_helped")
    kinds = {s["kind"] for s in j["suggestions"]}
    assert kinds <= {
        "surge_beds",
        "slow_spread",
        "shorten_closure",
        "cancel_closure",
        "restore_beds",
    }
    helped = [s["people_helped"] for s in j["suggestions"]]
    assert helped == sorted(helped, reverse=True)
    for s in j["suggestions"]:
        if s["apply"]["type"] == "add_event":  # an applied surge must be a valid event
            run = client.post(
                "/api/rn/run", json={**body, "events": [*body["events"], s["apply"]["event"]]}
            )
            assert run.status_code == 200


def test_rn_mitigate_nothing_to_fix():
    j = client.post("/api/rn/mitigate", json={"dataset": "golden", "r0": 0.5}).json()
    assert j["status"] == "nothing_to_fix" and j["suggestions"] == []

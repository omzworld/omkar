"""Step 5 definition of done, through the API the screens use: demo scenes 1 to 6 work without the command line.
Runs on a 20% sample in its own folder."""
import pytest
from fastapi.testclient import TestClient

from nba import spec
from nba.synth import generate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("api")
    generate(seed=5, scale=0.2, data_dir=d, log=lambda *_: None)
    mp = pytest.MonkeyPatch()
    mp.setattr(spec, "data_dir", lambda: d)
    from nba.api import app
    yield TestClient(app)
    mp.undo()


def test_scene_1_readiness(client):
    r = client.get("/api/readiness").json()
    assert r["history_weeks"] == 104 and all(c["within_5_points"] for c in r["consent"])


def test_scene_2_rule_studio_preview_and_save(client):
    p = client.post("/api/rules/R075/preview", json={"parameters": {"decline_pct": 6}}).json()
    assert p["after"] >= p["before"] and "-6" in p["condition_after"]
    v = client.post("/api/rules/R075/save", json={"parameters": {"decline_pct": 6}, "note": "test"}).json()
    assert v["version"] == 2
    assert client.get("/api/rules/R075").json()["parameters"]["decline_pct"] == 6
    assert client.post("/api/rules/R075/save", json={"parameters": {"nope": 1}}).status_code == 400


def test_scene_3_weekly_run_and_dial(client):
    full = client.post("/api/week", json={"week": 1, "dial": 1}).json()
    rules = client.post("/api/week", json={"week": 1, "dial": 0}).json()
    assert full["headline"]["actions sent"] > 0 and full["constraints"]
    assert full["headline"]["total expected return (EUR)"] >= rules["headline"]["total expected return (EUR)"]


def test_scenes_4_to_6_after_running_the_pilot(client):
    from nba import runner
    runner.run(4, log=lambda *_: None)          # week 4 completes November, the first sales month
    assert client.get("/api/pilot/status").json()["completed_weeks"] == 4
    d = client.get("/api/delivery/3").json()
    assert d["payload_count"] > 0 and d["reps_with_briefs"]
    user = d["reps_with_briefs"][0]["user_id"]
    u = client.get(f"/api/delivery/3/user/{user}").json()
    assert u["talk_track"]["grounding_check_passed"]
    assert client.get("/api/delivery/3/accounts").status_code == 200
    f = client.get("/api/feedback").json()
    assert f["weeks"] == 4 and f["by_rule"]
    for p in f["proposals"]:
        assert client.post(f"/api/feedback/proposals/{p['rule_id']}/approve").status_code == 200
    m = client.get("/api/measure?sales=20000000&savings=false").json()
    assert m["lift"]["months_measured"] >= 1 and len(m["gates"]) == 5
    assert m["return_model"]["baseline_sales_per_quarter_eur"] == 20000000


def test_return_model_break_even():
    import pandas as pd
    from nba.measure import return_model
    lift = {"months_measured": 3, "lift_pts": 2.0, "test_baseline_value_eur": 3_000_000}
    arms = pd.DataFrame({"pilot_arm": ["test", "control"], "cost_eur": [100.0, 100.0], "physicians": [10, 10]})
    rm = return_model(lift, arms, weeks=13, fee_per_quarter=180_000, margin_pct=60, count_touch_savings=False)
    # 3m sales a quarter x 60% margin: each point of lift is worth 18,000; the fee needs 10 points.
    assert rm["break_even_lift_pts"] == 10.0
    assert rm["net_benefit_per_quarter_eur"] == round(3_000_000 * 0.02 * 0.6 - 180_000)

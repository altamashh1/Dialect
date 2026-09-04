import io

import pandas as pd

from app.services.profiler import profile_dataframe


def test_profile_dataframe_basic():
    df = pd.DataFrame(
        {
            "age": [30, 25, None, 40],
            "city": ["NYC", "LA", "SF", "LA"],
            "active": [True, False, True, True],
        }
    )
    prof = profile_dataframe(df)

    assert prof["n_rows"] == 4
    assert prof["n_cols"] == 3

    age = prof["columns"]["age"]
    assert age["type"] == "float"
    assert age["null_count"] == 1
    assert age["min"] == 25
    assert age["max"] == 40

    city = prof["columns"]["city"]
    assert city["type"] == "string"
    assert city["unique_count"] == 3

    assert prof["columns"]["active"]["type"] == "boolean"
    assert len(prof["sample_rows"]) == 4
    # NaN must be JSON-safe
    assert prof["sample_rows"][2]["age"] is None


def test_profile_endpoint(auth_client):
    csv = b"x,y\n1,a\n2,b\n3,c\n"
    up = auth_client.post(
        "/api/datasets", files={"file": ("t.csv", io.BytesIO(csv), "text/csv")}
    )
    ds_id = up.json()["id"]

    resp = auth_client.get(f"/api/datasets/{ds_id}/profile")
    assert resp.status_code == 200
    prof = resp.json()
    assert prof["columns"]["x"]["type"] == "integer"
    assert prof["columns"]["y"]["sample_values"] == ["a", "b", "c"]


def test_profile_missing_404(auth_client):
    assert auth_client.get("/api/datasets/nope/profile").status_code == 404

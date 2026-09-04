import io
import json
import uuid

from app.services.datasets import _df_cache, _profile_cache

CSV = b"name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,SF\n"
ATTACKER_CSV = b"pwned\n1\n"


def _upload(client, name, data, ctype="text/csv"):
    return client.post(
        "/api/datasets", files={"file": (name, io.BytesIO(data), ctype)}
    )


def test_upload_requires_auth(client):
    assert _upload(client, "x.csv", CSV).status_code == 401


def test_upload_csv_returns_schema(auth_client):
    resp = _upload(auth_client, "people.csv", CSV)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_rows"] == 3
    assert body["n_cols"] == 3
    assert "id" in body

    got = auth_client.get(f"/api/datasets/{body['id']}")
    assert got.status_code == 200
    assert got.json()["filename"] == "people.csv"


def test_upload_json_records(auth_client):
    data = json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}]).encode()
    resp = _upload(auth_client, "d.json", data, "application/json")
    assert resp.status_code == 200
    assert resp.json()["n_rows"] == 2


def test_unsupported_type_rejected(auth_client):
    assert _upload(auth_client, "notes.txt", b"hello", "text/plain").status_code == 422


def test_empty_file_rejected(auth_client):
    assert _upload(auth_client, "empty.csv", b"").status_code == 400


def test_missing_dataset_404(auth_client):
    assert auth_client.get("/api/datasets/deadbeef").status_code == 404


def test_datasets_are_scoped_to_owner(auth_client, client):
    ds_id = _upload(auth_client, "mine.csv", CSV).json()["id"]

    other = client.post(
        "/api/auth/signup",
        json={"email": "other@example.com", "password": "password123"},
    ).json()["token"]
    resp = client.get(
        f"/api/datasets/{ds_id}", headers={"Authorization": f"Bearer {other}"}
    )
    assert resp.status_code == 404


def test_list_and_delete(auth_client):
    ds_id = _upload(auth_client, "a.csv", CSV).json()["id"]
    assert len(auth_client.get("/api/datasets").json()) == 1

    assert auth_client.delete(f"/api/datasets/{ds_id}").status_code == 200
    assert auth_client.get("/api/datasets").json() == []


def test_oversized_upload_is_rejected_before_it_is_buffered(auth_client, monkeypatch):
    """The cap must apply while reading, not after the whole file is in memory."""
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    oversized = b"a,b\n" + b"1,2\n" * 400_000  # ~2MB, over the 1MB cap
    resp = _upload(auth_client, "big.csv", oversized)
    assert resp.status_code == 413
    assert "1 MB" in resp.json()["detail"]


def test_upload_just_under_the_cap_succeeds(auth_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    rows = b"a,b\n" + b"1,2\n" * 20_000  # ~80KB
    assert _upload(auth_client, "small.csv", rows).status_code == 200


# --- Upload filenames are untrusted input -----------------------------------


def _signup(client):
    email = f"{uuid.uuid4().hex}@example.com"
    resp = client.post(
        "/api/auth/signup", json={"email": email, "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_upload_filename_cannot_overwrite_another_users_data(client):
    """A crafted upload filename must never reach the storage key.

    `"../<victim-dataset-id>/data.csv"` resolves back *inside* the storage root,
    so a containment check alone would let this land on the victim's blob and
    silently swap the data under every question they ask about it.
    """
    victim_token = _signup(client)
    client.headers.update({"Authorization": f"Bearer {victim_token}"})
    victim = _upload(client, "victim.csv", CSV).json()

    attacker_token = _signup(client)
    client.headers.update({"Authorization": f"Bearer {attacker_token}"})
    resp = _upload(client, f"../{victim['id']}/data.csv", ATTACKER_CSV)
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == "data.csv"  # a basename, never a path

    # Read through storage rather than the in-process DataFrame cache.
    _df_cache.clear()
    _profile_cache.clear()

    client.headers.update({"Authorization": f"Bearer {victim_token}"})
    profile = client.get(f"/api/datasets/{victim['id']}/profile").json()
    assert profile["n_rows"] == 3
    assert set(profile["columns"]) == {"name", "age", "city"}


def test_upload_filename_is_stored_as_a_basename(auth_client):
    body = _upload(auth_client, "reports/2024/q1 sales.csv", CSV).json()
    assert body["filename"] == "q1 sales.csv"


def test_over_long_filename_is_truncated_to_the_column_width(auth_client):
    body = _upload(auth_client, "a" * 400 + ".csv", CSV).json()
    assert len(body["filename"]) <= 255

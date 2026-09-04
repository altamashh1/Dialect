def test_signup_login_me(client):
    r = client.post(
        "/api/auth/signup", json={"email": "A@Example.com", "password": "password123"}
    )
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["email"] == "a@example.com"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"

    login = client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "password123"}
    )
    assert login.status_code == 200


def test_duplicate_email_rejected(client):
    body = {"email": "dup@example.com", "password": "password123"}
    assert client.post("/api/auth/signup", json=body).status_code == 200
    assert client.post("/api/auth/signup", json=body).status_code == 409


def test_short_password_rejected(client):
    r = client.post(
        "/api/auth/signup", json={"email": "x@example.com", "password": "short"}
    )
    assert r.status_code == 422


def test_bad_email_rejected(client):
    r = client.post(
        "/api/auth/signup", json={"email": "notanemail", "password": "password123"}
    )
    assert r.status_code == 422


def test_wrong_password_rejected(client):
    client.post(
        "/api/auth/signup", json={"email": "y@example.com", "password": "password123"}
    )
    r = client.post(
        "/api/auth/login", json={"email": "y@example.com", "password": "wrongpass1"}
    )
    assert r.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer garbage"}
        ).status_code
        == 401
    )

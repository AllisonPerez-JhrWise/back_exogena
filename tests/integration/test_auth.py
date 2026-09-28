async def test_register_login_and_me(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "Ana@Example.com",
            "password": "password-123",
            "first_name": "Ana",
            "middle_name": "María",
            "last_name": "Gómez",
        },
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["email"] == "ana@example.com"
    assert "password_hash" not in data["user"]
    assert "access_token" in response.cookies

    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ana@example.com", "password": "password-123"},
    )
    assert login.status_code == 200

    # La cookie HttpOnly que pone el login autentica la siguiente petición
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["data"]["full_name"] == "Ana María Gómez"
    assert me.json()["data"]["second_last_name"] is None
    assert "password_hash" not in me.text


async def test_duplicate_email_is_conflict(client, register):
    await register("dup@example.com")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "password-123",
            "first_name": "Dup",
            "last_name": "Licado",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_wrong_password_and_unknown_user_look_the_same(client, register):
    await register("bob@example.com")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "nope-nope"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_logout_clears_cookie(client, register):
    await register("carl@example.com")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "carl@example.com", "password": "password-123"},
    )
    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_register_requires_first_name_and_last_name(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "sin@apellido.co", "password": "password-123", "first_name": "Sin"},
    )
    assert response.status_code == 422
    assert response.json()["details"][0]["loc"] == "body.last_name"

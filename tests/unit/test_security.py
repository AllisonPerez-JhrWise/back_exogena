from datetime import timedelta

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed.startswith("$argon2")
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_without_hash_is_false():
    assert verify_password("anything", None) is False


def test_token_roundtrip_keeps_claims():
    token = create_access_token("user-1", claims={"email": "a@b.co"})
    claims = decode_access_token(token)
    assert claims["sub"] == "user-1"
    assert claims["email"] == "a@b.co"


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        create_access_token("user-1", expires_delta=timedelta(seconds=-1)),
        create_access_token("user-1")[:-2] + "xx",
    ],
    ids=["garbage", "expired", "tampered"],
)
def test_invalid_tokens_are_rejected(token):
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)

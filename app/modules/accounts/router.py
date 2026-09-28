import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.modules.accounts.dependencies import (
    ActiveUserDep,
    AuthServiceDep,
    GoogleClientDep,
)
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserRead,
)
from app.shared.responses import ApiResponse

auth_router = APIRouter()
users_router = APIRouter()

OAUTH_STATE_COOKIE = "oauth_state"


def _set_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
    )


def _login(response: Response, user: User, token: str) -> AuthResponse:
    _set_cookie(
        response,
        settings.auth_cookie_name,
        token,
        settings.access_token_expire_minutes * 60,
    )
    return AuthResponse(user=UserRead.model_validate(user), access_token=token)


# ── Email / contraseña ─────────────────────────────────────────────────────


@auth_router.post(
    "/register",
    response_model=ApiResponse[AuthResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(data: RegisterRequest, response: Response, service: AuthServiceDep):
    user = await service.register(data)
    return ApiResponse(
        message="Account created", data=_login(response, user, service.issue_token(user))
    )


@auth_router.post("/login", response_model=ApiResponse[AuthResponse])
async def login(data: LoginRequest, response: Response, service: AuthServiceDep):
    user = await service.authenticate(data.email, data.password)
    return ApiResponse(message="Logged in", data=_login(response, user, service.issue_token(user)))


@auth_router.post("/logout", response_model=ApiResponse[None])
async def logout(response: Response):
    response.delete_cookie(
        settings.auth_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
    )
    return ApiResponse(message="Logged out")


# ── Google OAuth ─────────────────────────────────────────────────────────


@auth_router.get("/google/login", response_class=RedirectResponse)
async def google_login(google: GoogleClientDep):
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(google.authorization_url(state))
    # Se verifica en el callback para prevenir CSRF en el login
    _set_cookie(redirect, OAUTH_STATE_COOKIE, state, max_age=600)
    return redirect


@auth_router.get("/google/callback", response_model=ApiResponse[AuthResponse])
async def google_callback(
    code: str,
    state: str,
    response: Response,
    google: GoogleClientDep,
    service: AuthServiceDep,
    oauth_state: Annotated[str | None, Cookie()] = None,
):
    if not oauth_state or not secrets.compare_digest(oauth_state, state):
        raise UnauthorizedError("Invalid OAuth state")

    user = await service.login_with_google(await google.fetch_user(code))
    token = service.issue_token(user)

    if settings.frontend_url:
        # Flujo del navegador: vuelve al front de Next.js con la cookie de sesión ya puesta
        redirect = RedirectResponse(settings.frontend_url, status_code=status.HTTP_302_FOUND)
        _login(redirect, user, token)
        redirect.delete_cookie(OAUTH_STATE_COOKIE, domain=settings.cookie_domain)
        return redirect

    response.delete_cookie(OAUTH_STATE_COOKIE, domain=settings.cookie_domain)
    return ApiResponse(message="Logged in", data=_login(response, user, token))


# ── Usuarios ────────────────────────────────────────────────────────────────


@users_router.get("/me", response_model=ApiResponse[UserRead])
async def me(user: ActiveUserDep):
    return ApiResponse(data=user)

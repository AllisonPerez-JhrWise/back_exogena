import logging
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.modules.accounts.schemas import GoogleUser

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class GoogleOAuthClient:
    def __init__(self, settings: Settings):
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri

    def authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "prompt": "select_account",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def fetch_user(self, code: str) -> GoogleUser:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
            )
            if token_response.status_code != 200:
                # Se registra la respuesta de Google en el log, nunca se devuelve al cliente
                logger.warning("Google token exchange failed: %s", token_response.text)
                raise UnauthorizedError("Google authentication failed")

            access_token = token_response.json().get("access_token")
            user_response = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            if user_response.status_code != 200:
                logger.warning("Google userinfo failed: %s", user_response.text)
                raise UnauthorizedError("Google authentication failed")

        return GoogleUser.model_validate(user_response.json())

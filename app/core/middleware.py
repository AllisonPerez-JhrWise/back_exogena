import logging
import re
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx

logger = logging.getLogger("app.request")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SILENT_PATHS = ("/health",)


class RequestContextMiddleware:
    """Asigna un id a cada petición (o reutiliza el X-Request-ID del ALB / BFF de Next),
    lo devuelve en la respuesta y escribe una línea de log por petición."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid4().hex
        token = request_id_ctx.set(request_id)
        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if not scope["path"].startswith(_SILENT_PATHS):
                logger.info(
                    "%s %s %s %.1fms",
                    scope["method"],
                    scope["path"],
                    status_code,
                    (time.perf_counter() - start) * 1000,
                )
            request_id_ctx.reset(token)

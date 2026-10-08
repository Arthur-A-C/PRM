"""Independent password gate for temporary public previews."""

import base64
import secrets

from starlette.responses import PlainTextResponse


class PreviewBasicAuth:
    def __init__(self, app, password: str, username: str = "prm-preview") -> None:
        if len(password) < 24:
            raise ValueError("A senha da prévia deve ter ao menos 24 caracteres.")
        self.app = app
        self.expected = b"Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8"))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = next(
            (value for name, value in scope.get("headers", ()) if name.lower() == b"authorization"),
            b"",
        )
        if not secrets.compare_digest(authorization, self.expected):
            response = PlainTextResponse(
                "Acesso de prévia restrito.",
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Basic realm="PRM Preview", charset="UTF-8"',
                    "Cache-Control": "no-store",
                },
            )
            await response(scope, receive, send)
            return

        async def guarded_send(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", ()))
                headers.extend([
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-robots-tag", b"noindex, nofollow"),
                ])
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, guarded_send)

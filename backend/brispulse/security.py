"""Response headers for security and caching (M5).

A plain ASGI middleware rather than Starlette's ``BaseHTTPMiddleware``, so streamed and
compressed responses pass through untouched; it only adds headers to the start message.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The web app loads its own files, plus map tiles, sprites and glyphs from OpenFreeMap.
# Inline style attributes are needed by React's style prop and by the map library.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://tiles.openfreemap.org",
        "font-src 'self'",
        "connect-src 'self' https://tiles.openfreemap.org",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)

# The interactive API documentation loads Swagger UI from a CDN, so it is left without
# a content security policy rather than half-broken by one.
_NO_CSP_PATHS = ("/docs", "/redoc", "/openapi.json")

_COMMON_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    # Ignored by browsers over plain HTTP, so harmless in local development.
    (b"strict-transport-security", b"max-age=31536000"),
)

# Built files carry a content hash in their name, so they never change once published.
IMMUTABLE = b"public, max-age=31536000, immutable"
# The page itself must be revalidated, or visitors keep an old page pointing at old files.
REVALIDATE = b"no-cache"


def _cache_control(path: str) -> bytes | None:
    if path.startswith("/assets/"):
        return IMMUTABLE
    if path in ("/", "/index.html"):
        return REVALIDATE
    return None


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                additions: list[tuple[bytes, bytes]] = [
                    header for header in _COMMON_HEADERS if header[0] not in present
                ]
                if not path.startswith(_NO_CSP_PATHS) and b"content-security-policy" not in present:
                    additions.append((b"content-security-policy", CONTENT_SECURITY_POLICY.encode()))
                cache = _cache_control(path)
                # Only a successful file gets long-lived caching; an error must not stick.
                if (
                    cache is not None
                    and b"cache-control" not in present
                    and message["status"] == 200
                ):
                    additions.append((b"cache-control", cache))
                message["headers"] = headers + additions
            await send(message)

        await self.app(scope, receive, send_with_headers)

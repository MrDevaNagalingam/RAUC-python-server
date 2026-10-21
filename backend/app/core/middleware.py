import logging
from uuid import uuid4

from starlette.responses import JSONResponse

log = logging.getLogger("ota")


class RequestPolicy:
    """Bound DDI bodies including chunked requests, correlate and sanitize request logs."""

    def __init__(self, app, max_body_bytes):
        self.app = app
        self.limit = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500

        async def send_with_headers(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        try:
            if scope["path"] == "/api/firmware/upload":
                # Authenticated upload endpoint parses multipart incrementally with its own limit.
                await self.app(scope, receive, send_with_headers)
            elif scope["method"] in {"PUT", "POST", "PATCH"}:
                body = bytearray()
                while True:
                    event = await receive()
                    if event["type"] == "http.disconnect":
                        return
                    body.extend(event.get("body", b""))
                    if len(body) > self.limit:
                        return await JSONResponse({"detail": "Request body too large"}, 413)(
                            scope, receive, send_with_headers
                        )
                    if not event.get("more_body", False):
                        break
                content_type = dict(scope["headers"]).get(b"content-type", b"")
                if body and content_type.split(b";", 1)[0].lower() != b"application/json":
                    return await JSONResponse({"detail": "Expected application/json"}, 415)(
                        scope, receive, send_with_headers
                    )
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                await self.app(scope, replay, send_with_headers)
            else:
                await self.app(scope, receive, send_with_headers)
        finally:
            route = scope.get("route")
            log.info(
                "http.request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                    }
                },
            )

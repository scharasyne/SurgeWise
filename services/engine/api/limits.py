"""Bound JSON request bodies before parsing (also for direct engine callers)."""
from starlette.responses import JSONResponse


class BodySizeLimit:
    def __init__(self, app, maximum=32768, route_limits=None):
        self.app = app
        self.maximum = maximum
        self.route_limits = route_limits or {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        maximum = self.route_limits.get(scope["path"], self.maximum)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > maximum:
                response = JSONResponse({"detail": {"code": "PAYLOAD_TOO_LARGE", "message": f"Maximum request body is {maximum // 1024} KB."}}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        return await self.app(scope, replay, send)

"""WSGI endpoint for web apps that call SurgeWise over HTTP."""

import json
from urllib.parse import parse_qs

from .history import gp_history
from .predictor import predict

FIELDS = {"weeks_ahead", "city_updates", "local_updates", "multiplier", "start", "duration", "ramp"}


def response(start_response, status, payload, extra_headers=()):
    body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json"), ("Content-Length", str(len(body))), *extra_headers
    ])
    return [body]


def history_response(environ, start_response):
    if environ.get("REQUEST_METHOD") != "GET":
        return response(start_response, "405 Method Not Allowed", {"error": "Use GET"}, [("Allow", "GET")])
    try:
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True, max_num_fields=3)
        if query.keys() - {"year", "week", "barangay_code"} or any(len(v) != 1 for v in query.values()):
            raise ValueError("Use year, week and barangay_code at most once each")
        params = {key: values[0] for key, values in query.items()}
        for key in ("year", "week"):
            if key in params:
                params[key] = int(params[key])
        result = gp_history(**params)
    except ValueError as error:
        return response(start_response, "400 Bad Request", {"error": str(error)})
    return response(start_response, "200 OK", result)


def application(environ, start_response):
    if environ.get("PATH_INFO") == "/gp-history":
        return history_response(environ, start_response)
    if environ.get("PATH_INFO") != "/predict":
        return response(start_response, "404 Not Found", {"error": "Unknown endpoint"})
    if environ.get("REQUEST_METHOD") != "POST":
        return response(start_response, "405 Method Not Allowed", {"error": "Use POST"}, [("Allow", "POST")])
    if environ.get("CONTENT_TYPE", "").split(";")[0].strip().lower() != "application/json":
        return response(start_response, "415 Unsupported Media Type", {"error": "Send application/json"})
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length <= 0:
            raise ValueError("Send a JSON object with a Content-Length header")
        if length > 2 * 1024 * 1024:
            return response(start_response, "413 Content Too Large", {"error": "Maximum body size is 2 MiB"})
        payload = json.loads(environ["wsgi.input"].read(length))
        if not isinstance(payload, dict) or payload.keys() - FIELDS:
            raise ValueError("Expected an object with supported prediction fields")
        result = predict(**payload)
    except (ValueError, RecursionError) as error:
        return response(start_response, "400 Bad Request", {"error": str(error)})
    return response(start_response, "200 OK", result)

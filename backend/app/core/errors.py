"""Structured error response utilities with i18n support."""

import logging

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

# Translatable generic error messages keyed by HTTP status code
_ERROR_MESSAGES = {
    "en": {
        400: "Bad request",
        401: "Authentication required",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        410: "Gone",
        422: "Validation error",
        429: "Too many requests",
        500: "An unexpected error occurred",
    },
    "fr": {
        400: "Requ\u00eate invalide",
        401: "Authentification requise",
        403: "Acc\u00e8s interdit",
        404: "Non trouv\u00e9",
        409: "Conflit",
        410: "Ressource expir\u00e9e",
        422: "Erreur de validation",
        429: "Trop de requ\u00eates",
        500: "Une erreur inattendue s'est produite",
    },
}


class ApiError(HTTPException):
    """HTTPException with a machine-readable ``error.code``.

    Clients branch on the code (e.g. ``EMAIL_NOT_VERIFIED``, ``QUOTA_EXCEEDED``,
    ``TOO_MANY_ATTEMPTS``); the message stays free text for people. Plain
    ``HTTPException`` keeps the default code ``HTTP_<status>``.
    """

    def __init__(self, status_code: int, detail: str, code: str, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def _get_locale(request: Request) -> str:
    """Extract preferred language from Accept-Language header."""
    accept = request.headers.get("accept-language", "en")
    # Simple parsing: take the first language code
    lang = accept.split(",")[0].split(";")[0].strip().lower()[:2]
    return lang if lang in _ERROR_MESSAGES else "en"


async def http_error_handler(request: Request, exc: HTTPException):
    """Return structured error responses for all HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": getattr(exc, "code", None) or f"HTTP_{exc.status_code}",
                "message": exc.detail,
            }
        },
        headers=getattr(exc, "headers", None) or None,
    )


async def validation_error_handler(request: Request, exc):
    """422 for malformed requests, in the same envelope as every other error.

    ``detail`` keeps FastAPI's per-field list for API clients; ``error.message``
    is a single readable sentence for user interfaces.
    """
    from fastapi.encoders import jsonable_encoder

    errors = exc.errors()
    parts = []
    for err in errors[:3]:
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        msg = err.get("msg", "invalid value")
        parts.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    lang = _get_locale(request)
    fallback = _ERROR_MESSAGES.get(lang, _ERROR_MESSAGES["en"])[422]
    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "VALIDATION_ERROR", "message": "; ".join(parts) or fallback},
            "detail": jsonable_encoder(errors, custom_encoder={Exception: str}),
        },
    )


async def generic_error_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — log and return generic 500."""
    _log.exception("Unhandled error on %s %s", request.method, request.url.path)
    lang = _get_locale(request)
    message = _ERROR_MESSAGES.get(lang, _ERROR_MESSAGES["en"]).get(500, "An unexpected error occurred")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
            }
        },
    )

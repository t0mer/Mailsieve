"""Validation endpoints (§6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_validation_service, rate_limit_validate, require_api
from app.providers.mailboxlayer.client import UpstreamError
from app.providers.mailboxlayer.secret import SecretUnavailable
from app.schemas.validation import ValidateRequest, ValidationResponse

if TYPE_CHECKING:
    from app.services.validation_service import ValidationService

router = APIRouter(prefix="/api/v1", tags=["validate"])

_UPSTREAM_DETAIL = "upstream verification endpoint is unreachable"


async def _run(
    svc: ValidationService, email: str, *, force: bool
) -> ValidationResponse:
    try:
        return await svc.validate(email, source="api", force=force)
    except (SecretUnavailable, UpstreamError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{_UPSTREAM_DETAIL}: {exc}",
        ) from exc


@router.post(
    "/validate",
    response_model=ValidationResponse,
    summary="Validate an email address",
    dependencies=[Depends(require_api), Depends(rate_limit_validate)],
)
async def validate_post(
    body: ValidateRequest,
    force: bool = False,
    svc: ValidationService = Depends(get_validation_service),
) -> ValidationResponse:
    return await _run(svc, body.email, force=force)


@router.get(
    "/validate/{email}",
    response_model=ValidationResponse,
    summary="Validate an email address (path form)",
    dependencies=[Depends(require_api), Depends(rate_limit_validate)],
)
async def validate_get(
    email: str,
    force: bool = False,
    svc: ValidationService = Depends(get_validation_service),
) -> ValidationResponse:
    return await _run(svc, email, force=force)

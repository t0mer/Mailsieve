from app.schemas.validation import ValidationResponse


def test_response_roundtrip_preserves_null_catch_all():
    r = ValidationResponse(
        email="u@e.com",
        email_raw="U@E.com",
        catch_all=None,
        verdict="deliverable",
        checked_at="2026-08-01T00:00:00Z",
        source="provider",
    )
    dumped = r.model_dump()
    assert dumped["catch_all"] is None
    assert dumped["provider"] == "mailboxlayer"
    assert dumped["cached"] is False

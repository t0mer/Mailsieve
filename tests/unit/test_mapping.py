from app.providers.mailboxlayer.mapping import to_schema

RAW = {
    "email": "u@e.com",
    "did_you_mean": "",
    "user": "u",
    "domain": "e.com",
    "format_valid": True,
    "mx_found": True,
    "smtp_check": True,
    "catch_all": None,
    "role": False,
    "free": False,
    "disposable": False,
    "score": 0.96,
}


def test_catch_all_null_preserved():
    r = to_schema(RAW, "u@e.com", "U@E.com")
    assert r["catch_all"] is None  # not coerced to False


def test_did_you_mean_empty_to_null():
    assert to_schema(RAW, "u@e.com", "U@E.com")["did_you_mean"] is None


def test_verdict_deliverable():
    assert to_schema(RAW, "u@e.com", "U@E.com")["verdict"] == "deliverable"


def test_verdict_undeliverable_no_mx():
    assert to_schema({**RAW, "mx_found": False}, "u@e.com", "x")["verdict"] == "undeliverable"


def test_verdict_undeliverable_bad_format():
    assert to_schema({**RAW, "format_valid": False}, "u@e.com", "x")["verdict"] == "undeliverable"


def test_verdict_risky_disposable():
    assert to_schema({**RAW, "disposable": True}, "u@e.com", "x")["verdict"] == "risky"


def test_verdict_risky_catch_all_precedes_deliverable():
    # smtp true but catch_all true -> risky (catch-all takes precedence)
    assert to_schema({**RAW, "catch_all": True}, "u@e.com", "x")["verdict"] == "risky"


def test_verdict_unknown_missing_smtp():
    assert to_schema({**RAW, "smtp_check": None}, "u@e.com", "x")["verdict"] == "unknown"


def test_email_raw_and_provider_and_source():
    r = to_schema(RAW, "u@e.com", "U@E.com")
    assert r["email_raw"] == "U@E.com"
    assert r["provider"] == "mailboxlayer"
    assert r["source"] == "provider"
    assert r["cached"] is False
    assert r["checked_at"].endswith("Z")

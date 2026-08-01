from app.providers.mailboxlayer.useragents import UserAgents


def test_bundled_loads_and_skips_comments():
    ua = UserAgents()
    assert len(ua) >= 1
    assert ua.pick().startswith("Mozilla/")


def test_override_file_and_comment_skipping(tmp_path):
    f = tmp_path / "ua.txt"
    f.write_text("# a comment\n\nAgent/1.0\nAgent/2.0\n")
    ua = UserAgents(str(f))
    assert len(ua) == 2
    assert ua.pick() in {"Agent/1.0", "Agent/2.0"}

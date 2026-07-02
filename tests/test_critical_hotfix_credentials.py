from app.credentials import merge_credentials_preserving_existing


def test_empty_credentials_do_not_overwrite_existing_login_password():
    existing = {"otrs": {"login": "user", "password": "secret"}}
    incoming = {"otrs": {"login": "", "password": ""}}
    assert merge_credentials_preserving_existing(existing, incoming)["otrs"] == existing["otrs"]

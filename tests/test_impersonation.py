"""The MCP listings reader can act as a read-only service account, built from the user's own credentials."""
from unittest import mock

from agent.core import listings


def test_no_env_means_the_credentials_are_used_as_they_are(monkeypatch):
    monkeypatch.delenv(listings.IMPERSONATE_ENV, raising=False)
    src = object()
    assert listings.impersonate(src, ["s"]) is src


def test_env_builds_impersonated_credentials_from_the_source(monkeypatch):
    monkeypatch.setenv(listings.IMPERSONATE_ENV, "ro@p.iam.gserviceaccount.com")
    src = object()
    with mock.patch("google.auth.impersonated_credentials.Credentials") as cls:
        out = listings.impersonate(src, ["https://www.googleapis.com/auth/datastore"])
    cls.assert_called_once_with(source_credentials=src, target_principal="ro@p.iam.gserviceaccount.com",
                                target_scopes=["https://www.googleapis.com/auth/datastore"], lifetime=3600)
    assert out is cls.return_value


def test_blank_env_is_ignored(monkeypatch):
    monkeypatch.setenv(listings.IMPERSONATE_ENV, "  ")
    src = object()
    assert listings.impersonate(src, []) is src

"""Errors whose message is safe and useful to show a user."""
from __future__ import annotations


class KodiWiseError(Exception):
    """A problem the assistant can explain to the user in plain words."""

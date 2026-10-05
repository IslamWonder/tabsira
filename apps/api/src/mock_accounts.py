"""
The addresses of the mock members that start the platform (decision 66, plan 23).

A mock member is recognised by its address alone, and such an address never receives mail: the
one function that talks to an SMTP server refuses it (`services/email_service.py`). The first
domain, `.invalid`, was refused by the sign-in schema, so accounts made on it could not sign in;
it stays here only so that the importer still finds, and removes, what an earlier run made.
"""

from __future__ import annotations

MOCK_DOMAIN = "mock.tabsira.me"
LEGACY_MOCK_DOMAIN = "mock.tabsira.invalid"
MOCK_DOMAINS = (MOCK_DOMAIN, LEGACY_MOCK_DOMAIN)


def is_mock_address(address: str) -> bool:
    """Whether the address is on a reserved mock domain, whatever its case or surrounding space."""
    domain = address.strip().rpartition("@")[2].strip(" >").lower()
    return domain in MOCK_DOMAINS


def mock_email(handle: str) -> str:
    """Return the reserved address of a mock member's handle."""
    return f"{handle.lower()}@{MOCK_DOMAIN}"

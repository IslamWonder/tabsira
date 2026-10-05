from __future__ import annotations

import pytest

from src import mock_accounts


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("amal@mock.tabsira.me", True),
        (" AMAL@MOCK.TABSIRA.ME ", True),
        ("amal@mock.tabsira.invalid", True),
        ("Amal <amal@mock.tabsira.me>", True),
        ("amal@tabsira.me", False),
        ("amal@evil-mock.tabsira.me", False),
        ("amal@mock.tabsira.me.evil.com", False),
        ("mock.tabsira.me", True),
        ("", False),
    ],
)
def test_only_the_reserved_domains_are_mock_addresses(address: str, expected: bool) -> None:
    assert mock_accounts.is_mock_address(address) is expected


def test_a_mock_address_is_the_lower_cased_handle_on_the_new_domain() -> None:
    assert mock_accounts.mock_email("Amal_TN") == "amal_tn@mock.tabsira.me"

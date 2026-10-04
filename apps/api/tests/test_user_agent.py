"""The user agent is reduced to a family, so nothing finer is ever kept."""

from __future__ import annotations

import pytest

from src.user_agent import FAMILIES, OTHER, user_agent_family

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


@pytest.mark.parametrize(
    ("header", "family"),
    [
        (CHROME, "chrome"),
        (CHROME + " Edg/131.0.0.0", "edge"),
        (CHROME + " OPR/115.0.0.0", "opera"),
        (CHROME.replace("Chrome/131", "SamsungBrowser/26.0 Chrome/131"), "samsung_internet"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0", "firefox"),
        ("Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 FxiOS/132.0 Mobile Safari/605.1.15", "firefox"),
        ("Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 CriOS/131.0 Mobile Safari/604.1", "chrome"),
        ("Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 Version/18.1 Mobile Safari/604.1", "safari"),
        ("curl/8.5.0", OTHER),
        ("", OTHER),
        (None, OTHER),
    ],
)
def test_a_header_is_reduced_to_its_family(header, family):
    assert user_agent_family(header) == family
    assert family in FAMILIES


def test_the_family_names_nothing_finer_than_the_browser():
    # Neither the version nor the operating system survive.
    assert user_agent_family(CHROME) == "chrome"
    assert not any(part in user_agent_family(CHROME) for part in ("131", "Windows", "x64"))


def test_only_the_start_of_an_oversized_header_is_read():
    assert user_agent_family("x" * 600 + " Firefox/130.0") == OTHER

"""`messages_for` follows DEFAULT_LANGUAGE and SUPPORTED_LANGUAGES."""

from __future__ import annotations

import dataclasses

import pytest

from src import messages


@pytest.fixture
def english(monkeypatch):
    """A second catalog, as a stand-in for the day a language is added."""
    catalog = dataclasses.replace(messages.ARABIC, language="en", site_name="Tabsira")
    monkeypatch.setitem(messages.CATALOGS, "en", catalog)
    return catalog


def test_arabic_is_the_catalog_when_nothing_else_is_asked_for(make_settings):
    settings = make_settings()

    assert messages.messages_for("ar", settings=settings) is messages.ARABIC
    assert messages.messages_for(None, settings=settings) is messages.ARABIC
    assert messages.messages_for("xx", settings=settings) is messages.ARABIC
    assert messages.ARABIC.direction == "rtl"


def test_the_process_settings_are_read_when_none_are_given():
    assert messages.messages_for() is messages.ARABIC


def test_a_supported_language_with_a_catalog_is_served(make_settings, english):
    settings = make_settings(supported_languages="ar,en")

    assert messages.messages_for("en", settings=settings) is english


def test_a_language_the_settings_do_not_support_falls_back_to_the_default(make_settings, english):
    settings = make_settings(supported_languages="ar")

    assert messages.messages_for("en", settings=settings) is messages.ARABIC


def test_the_default_language_setting_chooses_the_catalog_when_none_is_asked_for(
    make_settings, english
):
    settings = make_settings(supported_languages="ar,en", default_language="en")

    assert messages.messages_for(None, settings=settings) is english


def test_a_supported_language_without_a_catalog_falls_back_to_arabic(make_settings):
    settings = make_settings(supported_languages="ar,fr", default_language="fr")

    assert messages.messages_for("fr", settings=settings) is messages.ARABIC

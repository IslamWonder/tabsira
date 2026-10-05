"""What the server says about where photos are kept (decision 44)."""

from __future__ import annotations

import logging

import pytest

from src import main
from src.cli import check_config
from src.storage import notice
from src.storage.notice import announce_storage, storage_notice

PRODUCTION = {
    "environment": "production",
    "site_url": "https://tabsira.me",
    "api_url": "https://api.tabsira.me",
    "admin_url": "https://admin.tabsira.me",
    "cors_origins": "https://tabsira.me",
    "session_cookie_domain": ".tabsira.me",
    "hash_secret": "not-a-real-secret-but-long-enough-for-the-rule",
    "ai_ovh": {"api_key": "ovh-key-123"},
    "ai_openai": {"api_key": "openai-key-123"},
    "disabled_features": "admin",
    "redis_password": "redis-secret",
    "s3_bucket": "tabsira-photos",
    "s3_access_key_id": "AKIAEXAMPLE",
    "s3_secret_access_key": "s3-secret-value",
    "s3_public_base_url": "https://media.tabsira.me",
}


@pytest.fixture(autouse=True)
def _forget_announcements() -> None:
    notice._announced.clear()


def test_without_a_bucket_the_notice_names_the_folder_and_that_production_requires_s3(
    make_settings, tmp_path
):
    text = storage_notice(make_settings(local_media_dir=str(tmp_path)))

    assert text == f"No S3 bucket: photos go to {tmp_path.resolve()}; production requires S3."


def test_a_bucket_says_nothing(make_settings):
    assert storage_notice(make_settings(**PRODUCTION)) is None


def test_the_warning_is_logged_once_per_process(make_settings, tmp_path, caplog):
    settings = make_settings(local_media_dir=str(tmp_path))
    with caplog.at_level(logging.INFO, logger="tabsira.storage"):
        announce_storage(settings)
        announce_storage(settings)
        announce_storage(make_settings(**PRODUCTION))

    assert [(r.levelno, r.name) for r in caplog.records] == [(logging.WARNING, "tabsira.storage")]


def test_building_the_application_announces_the_store_once(make_settings, tmp_path, caplog):
    settings = make_settings(local_media_dir=str(tmp_path))
    with caplog.at_level(logging.INFO, logger="tabsira.storage"):
        main.create_app(settings)
        main.create_app(settings)

    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_check_config_prints_the_warning_in_development(make_settings, tmp_path):
    lines = check_config.report(make_settings(local_media_dir=str(tmp_path)))

    assert "photos: local" in lines
    assert any(line.startswith("WARNING: No S3 bucket: photos go to") for line in lines)


def test_check_config_prints_no_warning_for_s3(make_settings):
    lines = check_config.report(make_settings(**PRODUCTION))

    assert "photos: s3" in lines
    assert not any("No S3 bucket" in line for line in lines)

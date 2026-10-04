"""
The two Alembic chains.

The first two tests read the migrations as text and as code. The rest run both
chains against the test database through the real `alembic` command, then put
the schema back the way the other tests expect it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text

from alembic import op
from src.models.scripture import GUARDED_TABLES
from tests.dbschema import EXTENSIONS, create_schema, reset_schemas

API_DIR = Path(__file__).resolve().parents[1]
APP_CONFIG = "alembic.ini"
GEODATA_CONFIG = "alembic_geodata/alembic.ini"
APP_TABLES = {
    "users",
    "oauth_accounts",
    "sessions",
    "profiles",
    "consents",
    "cookie_consents",
    "email_tokens",
    "login_attempts",
    "oauth_states",
    "ontology_entities",
    "ontology_candidates",
    "learning_path_versions",
    "learning_domains",
    "learning_units",
    "learner_unit_states",
    "quran_surahs",
    "quran_verses",
    "quran_verse_history",
    "quran_verse_search",
    "quran_annotations",
    "hadith_collections",
    "hadiths",
    "hadith_search",
    "hadith_signals",
    "hadith_rulings",
    "hadith_verification_queue",
    "scripture_audit",
    "scripture_sync_state",
    "admin_audit_log",
    "admin_sessions",
    "admin_totp",
    "follows",
    "blocks",
    "insight_publications",
    "posts",
    "post_likes",
    "bookmarks",
    "comments",
    "reports",
    "moderation_actions",
    "guests",
    "scans",
    "insights",
    "insight_chat_messages",
    "world_places",
    "world_relations",
    "treasures",
    "scan_events",
    "ai_calls",
    "evidence_exposures",
}


def load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic(config: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the alembic command for one chain against the test database."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", config, *arguments],
        cwd=API_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_the_app_chain_creates_every_extension_in_public_and_skips_none(monkeypatch):
    migration = load(next((API_DIR / "alembic" / "versions").glob("*_enable_extensions.py")))
    statements: list[str] = []
    monkeypatch.setattr(op, "execute", statements.append, raising=False)

    migration.upgrade()

    assert set(migration.EXTENSIONS) == set(EXTENSIONS)
    assert statements == [
        f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public'
        for extension in migration.EXTENSIONS
    ]
    # No error handling around the statements: a missing extension must raise.
    source = (API_DIR / "alembic" / "versions" / f"{migration.__name__}.py").read_text()
    assert "except" not in source
    assert "suppress" not in source


def test_each_chain_is_one_line_from_exactly_one_initial_revision():
    for chain in ("alembic", "alembic_geodata"):
        revisions = [load(path) for path in (API_DIR / chain / "versions").glob("2*.py")]
        by_id = {revision.revision: revision for revision in revisions}

        roots = [revision for revision in revisions if revision.down_revision is None]
        parents = [revision.down_revision for revision in revisions if revision.down_revision]
        assert len(roots) == 1
        # Every other revision names one that exists, and no two share a parent: no fork.
        assert set(parents) <= set(by_id)
        assert len(parents) == len(set(parents)) == len(revisions) - 1


@pytest.fixture
async def migrated(engine):
    """An empty `app` and `geodata`, for the chains to build; the test schema is restored after."""
    async with engine.begin() as connection:
        await reset_schemas(connection)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await create_schema(connection)


async def test_both_chains_build_the_database_and_match_the_models(migrated):
    geodata = alembic(GEODATA_CONFIG, "upgrade", "head")
    app = alembic(APP_CONFIG, "upgrade", "head")
    assert geodata.returncode == 0, geodata.stderr
    assert app.returncode == 0, app.stderr

    async with migrated.connect() as connection:
        tables = set(
            (
                await connection.execute(
                    text(
                        "SELECT schemaname || '.' || tablename FROM pg_tables "
                        "WHERE schemaname IN ('app', 'geodata')"
                    )
                )
            ).scalars()
        )
        extensions = set(
            (await connection.execute(text("SELECT extname FROM pg_extension"))).scalars()
        )
        versions = {
            schema: (
                await connection.execute(
                    text(f"SELECT version_num FROM {schema}.alembic_version")  # noqa: S608
                )
            ).scalar_one()
            for schema in ("app", "geodata")
        }
        indexes = set(
            (
                await connection.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'geonames'")
                )
            ).scalars()
        )
        views = set(
            (
                await connection.execute(
                    text(
                        "SELECT schemaname || '.' || matviewname || ' ' || ispopulated "
                        "FROM pg_matviews WHERE schemaname IN ('app', 'geodata')"
                    )
                )
            ).scalars()
        )
        triggers = set(
            (
                await connection.execute(
                    text(
                        "SELECT c.relname || '.' || t.tgname FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid = t.tgrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'app' AND NOT t.tgisinternal"
                    )
                )
            ).scalars()
        )

    assert {
        "geodata.geonames",
        "geodata.geonames_alternate_names",
        "geodata.geonames_hierarchy",
        "geodata.geonames_postal_codes",
        "geodata.geonames_country_info",
        "geodata.alembic_version",
        "app.alembic_version",
        *(f"app.{table}" for table in APP_TABLES),
    } == tables
    assert set(EXTENSIONS) <= extensions
    assert versions == {"app": "20261004_181000", "geodata": "20261004_130000"}
    # alembic check cannot see a materialized view either.
    assert views == {"app.quran_verse_spans true"}
    # The models and the migrations describe the same database.
    assert {"ix_geonames_name_trgm", "ix_geonames_location_geom", "pk_geonames"} <= indexes
    # The scripture write guard exists after the migrations too, not only in a schema built
    # from the models; alembic check cannot see triggers.
    assert {
        f"{table}.{table}_{kind}_guard"
        for table in GUARDED_TABLES
        for kind in ("write", "truncate")
    } <= triggers
    # So does the cookie-consent guard.
    assert {
        "cookie_consents.cookie_consents_row_guard",
        "cookie_consents.cookie_consents_truncate_guard",
    } <= triggers
    for config in (GEODATA_CONFIG, APP_CONFIG):
        check = alembic(config, "check")
        assert check.returncode == 0, check.stdout + check.stderr


async def test_the_geodata_chain_downgrades_and_upgrades_again(migrated):
    assert alembic(GEODATA_CONFIG, "upgrade", "head").returncode == 0

    down = alembic(GEODATA_CONFIG, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    async with migrated.connect() as connection:
        left = (
            await connection.execute(
                text("SELECT count(*) FROM pg_tables WHERE tablename LIKE 'geonames%'")
            )
        ).scalar_one()
    assert left == 0

    again = alembic(GEODATA_CONFIG, "upgrade", "head")
    assert again.returncode == 0, again.stderr


async def test_the_app_chain_is_safe_to_run_twice_and_downgrades_without_dropping_extensions(
    migrated,
):
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    assert alembic(APP_CONFIG, "downgrade", "base").returncode == 0
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0

    async with migrated.connect() as connection:
        extensions = set(
            (await connection.execute(text("SELECT extname FROM pg_extension"))).scalars()
        )
    assert set(EXTENSIONS) <= extensions


async def test_alembic_check_sees_a_difference_between_the_models_and_the_database(migrated):
    # The check must not pass vacuously: it once skipped the `app` schema entirely.
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    async with migrated.begin() as connection:
        await connection.execute(text("ALTER TABLE app.users ADD COLUMN drift integer"))
        await connection.execute(text("ALTER TABLE app.quran_surahs ADD COLUMN drift integer"))

    check = alembic(APP_CONFIG, "check")

    assert check.returncode != 0
    assert "drift" in check.stdout + check.stderr


async def test_the_app_chain_builds_the_append_only_trigger_and_removes_it_again(migrated):
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    async with migrated.begin() as connection:
        user_id = (
            await connection.execute(
                text(
                    "INSERT INTO app.users (email, display_name) VALUES ('a@example.com', 'A') RETURNING id"
                )
            )
        ).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO app.consents (user_id, kind, version, granted) VALUES (:u, 'terms', 'v1', true)"
            ),
            {"u": user_id},
        )

    with pytest.raises(Exception, match="append-only"):
        async with migrated.begin() as connection:
            await connection.execute(text("UPDATE app.consents SET granted = false"))

    assert alembic(APP_CONFIG, "downgrade", "base").returncode == 0
    async with migrated.connect() as connection:
        functions = (
            await connection.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'consents_forbid_update'")
            )
        ).scalar_one()
        tables = (
            await connection.execute(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'app'")
            )
        ).scalar_one()
    # Only the version table is left, and no function.
    assert (functions, tables) == (0, 1)


async def test_the_migration_builds_the_trigram_index_the_resolver_relies_on(migrated):
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0

    async with migrated.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_ontology_entities_search_text_trgm'"
                )
            )
        ).scalar_one()

    assert "USING gin (search_text gin_trgm_ops)" in definition


async def test_the_app_chain_builds_the_cookie_consent_guard_and_removes_it_again(migrated):
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    async with migrated.begin() as connection:
        user_id = (
            await connection.execute(
                text(
                    "INSERT INTO app.users (email, display_name) "
                    "VALUES ('a@example.com', 'A') RETURNING id"
                )
            )
        ).scalar_one()
        for owner in (user_id, None):
            await connection.execute(
                text(
                    "INSERT INTO app.cookie_consents "
                    "(consent_id, policy_version, analytics, behaviour, user_agent_family, user_id) "
                    "VALUES (gen_random_uuid(), 'v1', true, false, 'firefox', :owner)"
                ),
                {"owner": owner},
            )

    for statement in (
        "UPDATE app.cookie_consents SET analytics = false",
        "DELETE FROM app.cookie_consents",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with migrated.begin() as connection:
                await connection.execute(text(statement))
    # The account's own deletion takes its rows with it, and leaves the anonymous one.
    async with migrated.begin() as connection:
        await connection.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": user_id})
        left = (await connection.execute(text("SELECT user_id FROM app.cookie_consents"))).all()
    assert [row.user_id for row in left] == [None]

    # Down to the revision under cookie consents by name: a later migration must not shift it.
    assert alembic(APP_CONFIG, "downgrade", "20261004_121500").returncode == 0
    async with migrated.connect() as connection:
        functions = (
            await connection.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'cookie_consents_guard'")
            )
        ).scalar_one()
        tables = (
            await connection.execute(
                text("SELECT count(*) FROM pg_tables WHERE tablename = 'cookie_consents'")
            )
        ).scalar_one()
    assert (functions, tables) == (0, 0)


async def test_the_social_migration_makes_public_id_tables_and_removes_everything_it_made(migrated):
    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    tables = ("insight_publications", "posts", "comments", "reports")

    async def present():
        async with migrated.connect() as connection:
            sequences = set(
                (
                    await connection.execute(
                        text("SELECT sequencename FROM pg_sequences WHERE schemaname = 'app'")
                    )
                ).scalars()
            )
            defaults = (
                await connection.execute(
                    text(
                        "SELECT table_name, column_default FROM information_schema.columns "
                        "WHERE table_schema = 'app' AND column_name = 'id' "
                        "AND table_name = ANY(:tables)"
                    ),
                    {"tables": list(tables)},
                )
            ).all()
            triggers = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_proc WHERE proname IN "
                        "('insight_publications_forbid_update', 'moderation_actions_forbid_change')"
                    )
                )
            ).scalar_one()
        return sequences, defaults, triggers

    sequences, defaults, triggers = await present()
    assert {f"{table}_id_seq" for table in tables} <= sequences
    assert {row.table_name for row in defaults} == set(tables)
    assert all("timestamp_id" in row.column_default for row in defaults)
    assert triggers == 2

    # Down to the revision before the social network, by name: a later migration must not shift it.
    assert alembic(APP_CONFIG, "downgrade", "20261004_170000").returncode == 0
    sequences, defaults, triggers = await present()
    assert not {f"{table}_id_seq" for table in tables} & sequences
    assert defaults == []
    assert triggers == 0

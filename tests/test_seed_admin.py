"""
Tests for the script that creates the administrator account.

What matters about this script is almost entirely what it refuses to do. It
must not invent an address, it must not fall back to a known password, and it
must not hash a password too short to be one. Those are the three ways a
script like this ends up putting a usable credential into a repository, so
each of them is a test.

The rest is the three states it has to handle: no account with that address, an
account that exists and should be promoted, and a promotion that must be taken
back.

The database is pointed at a temporary file through ``DATABASE_URL``, because
the script opens its own engine: it is run from a shell rather than through
the API, so there is no session dependency to override.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from scripts import seed_admin
from src.db import Base, Mentor, create_db_engine
from src.mentor import security

ADDRESS = "admin@example.com"
CHOSEN_PASSWORD = "a-long-enough-password"


@pytest.fixture
def sessions(tmp_path, monkeypatch) -> sessionmaker[Session]:
    """A fresh database, with the script's own engine pointed at it."""
    url = f"sqlite:///{tmp_path / 'admin.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture(autouse=True)
def no_inherited_environment(monkeypatch):
    """
    Neither variable is set unless a test sets it.

    Without this, a developer who has ADMIN_PASSWORD exported would run a
    different test suite from everybody else, and the test that checks the
    generated path would quietly stop checking it.
    """
    monkeypatch.delenv(seed_admin.EMAIL_VARIABLE, raising=False)
    monkeypatch.delenv(seed_admin.PASSWORD_VARIABLE, raising=False)


def account(sessions) -> Mentor | None:
    with sessions() as session:
        return session.scalar(select(Mentor))


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------
def test_it_stops_without_an_address(sessions, capsys):
    """There is no default address, so there is nothing to create."""
    assert seed_admin.main([]) == 1

    assert "ADMIN_EMAIL" in capsys.readouterr().err
    assert account(sessions) is None


def test_it_refuses_a_password_that_is_too_short(sessions, monkeypatch, capsys):
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)
    monkeypatch.setenv(seed_admin.PASSWORD_VARIABLE, "short")

    assert seed_admin.main([]) == 1

    assert "shorter than" in capsys.readouterr().err
    assert account(sessions) is None


def test_there_is_no_default_password_in_the_source():
    """
    The script carries no password and no address, as its own source.

    A default would be a credential in the repository, in every clone of it
    and in its history. This reads the file rather than trusting the review
    that put it there.
    """
    from pathlib import Path

    source = Path(seed_admin.__file__).read_text(encoding="utf-8")

    # The two names are mentioned; no value for either is written down.
    assert "ADMIN_PASSWORD" in source
    for banned in ('password = "', "password='", "DEFAULT_PASSWORD", "admin123"):
        assert banned not in source


# ---------------------------------------------------------------------------
# Creating the account
# ---------------------------------------------------------------------------
def test_it_creates_an_administrator_with_the_password_it_was_given(
    sessions, monkeypatch, capsys
):
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)
    monkeypatch.setenv(seed_admin.PASSWORD_VARIABLE, CHOSEN_PASSWORD)

    assert seed_admin.main([]) == 0

    stored = account(sessions)
    assert stored.email == ADDRESS
    assert stored.is_admin is True
    assert security.verify_password(CHOSEN_PASSWORD, stored.password_hash)
    # An administrator is not a mentor the platform has checked, and not a
    # demonstration row either.
    assert stored.verified is False
    assert stored.is_demo is False

    printed = capsys.readouterr().out
    # A password the operator chose is one they already have, so it is not
    # echoed into a terminal history or a deployment log.
    assert CHOSEN_PASSWORD not in printed


def test_it_generates_and_prints_a_password_when_none_is_set(
    sessions, monkeypatch, capsys
):
    """
    Printed once, because only the hash is stored.

    There is nothing to recover it from afterwards, so a run that did not
    print it would create an account nobody could sign in to.
    """
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)

    assert seed_admin.main([]) == 0

    printed = capsys.readouterr().out
    generated = next(
        line.split("password:", 1)[1].strip()
        for line in printed.splitlines()
        if "password:" in line
    )
    assert len(generated) >= security.PASSWORD_MIN_LENGTH

    stored = account(sessions)
    assert security.verify_password(generated, stored.password_hash)


def test_two_runs_generate_two_different_passwords(sessions, monkeypatch, capsys):
    """
    The generated password is random, not derived from the address.

    A password derived from anything about the account would be one anybody
    with the script could work out.
    """
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)

    seed_admin.main([])
    first = capsys.readouterr().out
    seed_admin.main([])
    second = capsys.readouterr().out

    assert first != second


def test_the_address_is_matched_without_regard_to_capitals(sessions, monkeypatch):
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, "Admin@Example.COM")
    monkeypatch.setenv(seed_admin.PASSWORD_VARIABLE, CHOSEN_PASSWORD)

    assert seed_admin.main([]) == 0

    stored = account(sessions)
    assert stored.email == ADDRESS


# ---------------------------------------------------------------------------
# Updating an account that already exists
# ---------------------------------------------------------------------------
def test_it_promotes_an_existing_account_rather_than_adding_a_second(
    sessions, monkeypatch
):
    with sessions() as session:
        session.add(
            Mentor(
                full_name="A. Mentor",
                email=ADDRESS,
                password_hash=security.hash_password("the-original-password"),
            )
        )
        session.commit()

    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)
    monkeypatch.setenv(seed_admin.PASSWORD_VARIABLE, CHOSEN_PASSWORD)
    assert seed_admin.main([]) == 0

    with sessions() as session:
        every = session.scalars(select(Mentor)).all()
    assert len(every) == 1
    assert every[0].is_admin is True
    # The password was reset, which is the documented behaviour: the point of
    # running this against an existing account is usually that nobody has the
    # old one.
    assert security.verify_password(CHOSEN_PASSWORD, every[0].password_hash)


def test_keep_password_promotes_without_touching_the_password(sessions, monkeypatch):
    with sessions() as session:
        session.add(
            Mentor(
                full_name="A. Mentor",
                email=ADDRESS,
                password_hash=security.hash_password("the-original-password"),
            )
        )
        session.commit()

    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)
    assert seed_admin.main(["--keep-password"]) == 0

    stored = account(sessions)
    assert stored.is_admin is True
    assert security.verify_password("the-original-password", stored.password_hash)


def test_keep_password_refuses_to_create_an_account(sessions, monkeypatch, capsys):
    """An account has to be created with a password, so there is none to keep."""
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)

    assert seed_admin.main(["--keep-password"]) == 1

    assert "no password to keep" in capsys.readouterr().err
    assert account(sessions) is None


def test_revoke_clears_the_flag_and_leaves_the_account(sessions, monkeypatch):
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)
    monkeypatch.setenv(seed_admin.PASSWORD_VARIABLE, CHOSEN_PASSWORD)
    seed_admin.main([])

    assert seed_admin.main(["--revoke"]) == 0

    stored = account(sessions)
    assert stored is not None
    assert stored.is_admin is False
    assert security.verify_password(CHOSEN_PASSWORD, stored.password_hash)


def test_revoke_on_an_unknown_address_fails(sessions, monkeypatch, capsys):
    monkeypatch.setenv(seed_admin.EMAIL_VARIABLE, ADDRESS)

    assert seed_admin.main(["--revoke"]) == 1

    assert "no account is registered" in capsys.readouterr().err

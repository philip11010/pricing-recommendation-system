"""
Create or update the one account that may read the operations dashboard.

Administration is a flag on an ordinary account rather than a second kind of
user, so this script does one of three things to one row: creates the account
with the flag set, sets the flag on an account that already exists, or resets
its password. There is no endpoint that grants the flag, because granting it
over the API would make the gate on /admin something the API could be talked
into opening.

**There is no default password anywhere, and there is no default address.**
``ADMIN_EMAIL`` is required and the script stops without it. ``ADMIN_PASSWORD``
is optional, and when it is unset a strong one is generated with
``secrets.token_urlsafe`` and printed once, at the end of the run. It is
printed because it is the only time anybody will see it: only the Argon2 hash
is stored, so a lost password means running this script again rather than
recovering the old one.

A password baked into a script, a settings file or a documented default is a
password that is in the repository, in every clone of it and in its history.
That is the reason for the shape of this script, and the reason it will refuse
a short password rather than hash whatever it was given.

Run from the project root, against the database ``DATABASE_URL`` points at:

    # a generated password, printed once
    ADMIN_EMAIL=admin@example.com python scripts/seed_admin.py

    # a password you choose
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=... python scripts/seed_admin.py

    # take the flag away again, leaving the account and its password alone
    ADMIN_EMAIL=admin@example.com python scripts/seed_admin.py --revoke

On PowerShell, set the variables first:

    $env:ADMIN_EMAIL = "admin@example.com"
    python scripts/seed_admin.py

The schema has to exist first, so run ``alembic upgrade head`` before this.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db import Mentor, create_db_engine  # noqa: E402
from src.mentor import security  # noqa: E402

EMAIL_VARIABLE = "ADMIN_EMAIL"
PASSWORD_VARIABLE = "ADMIN_PASSWORD"

# How many random bytes a generated password is made of. 24 bytes is 32
# characters of URL-safe base64 and about 192 bits of entropy, which is far
# past anything a password policy asks for and is no harder to paste once.
GENERATED_BYTES = 24

# What the account is called. An administrator account is not a mentor on the
# platform, so it carries no profile text, no headline and no service: just a
# name, an address and the flag. The name is the only one of the three that
# has to say something, and it says what the account is.
ADMIN_NAME = "Platform administrator"

MISSING_EMAIL = (
    f"FAILED: set {EMAIL_VARIABLE} to the address the administrator signs in "
    f"with. There is no default address, on purpose."
)

SHORT_PASSWORD = (
    f"FAILED: {PASSWORD_VARIABLE} is shorter than {security.PASSWORD_MIN_LENGTH} characters. "
    f"Leave it unset to have a strong one generated instead."
)


def admin_email() -> str | None:
    """The address from the environment, normalised, or None if unset."""
    raw = (os.environ.get(EMAIL_VARIABLE) or "").strip()
    return security.normalise_email(raw) if raw else None


def admin_password() -> tuple[str, bool]:
    """
    The password to set, and whether this run generated it.

    The flag is what decides whether the password is printed. A password the
    operator chose is one they already have, and printing it would write it
    into a terminal history and a deployment log for no benefit.
    """
    given = os.environ.get(PASSWORD_VARIABLE)
    if given:
        return given, False
    return secrets.token_urlsafe(GENERATED_BYTES), True


def find_account(session: Session, email: str) -> Mentor | None:
    """The account registered to one address, matched without case."""
    return session.scalar(select(Mentor).where(func.lower(Mentor.email) == email))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update the one account that may read the operations "
            "dashboard under /admin. The address comes from ADMIN_EMAIL and "
            "the password from ADMIN_PASSWORD, or is generated and printed "
            "once when that is unset."
        )
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help=(
            "clear the administrator flag on the account and change nothing "
            "else, leaving the account and its password as they are"
        ),
    )
    parser.add_argument(
        "--keep-password",
        action="store_true",
        help=(
            "set the flag on an account that already exists without touching "
            "its password. Fails if the account does not exist yet, because "
            "an account has to be created with one"
        ),
    )
    arguments = parser.parse_args(argv)

    email = admin_email()
    if email is None:
        print(MISSING_EMAIL, file=sys.stderr)
        return 1

    password, generated = admin_password()
    if not arguments.revoke and not arguments.keep_password:
        if len(password) < security.PASSWORD_MIN_LENGTH:
            print(SHORT_PASSWORD, file=sys.stderr)
            return 1

    engine = create_db_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            account = find_account(session, email)

            if arguments.revoke:
                if account is None:
                    print(
                        "FAILED: no account is registered with that address.",
                        file=sys.stderr,
                    )
                    return 1
                was = bool(account.is_admin)
                account.is_admin = False
                session.commit()
                print(
                    f"Account {account.id} is no longer an administrator."
                    if was
                    else f"Account {account.id} was not an administrator."
                )
                return 0

            if account is None:
                if arguments.keep_password:
                    print(
                        "FAILED: no account is registered with that address, so "
                        "there is no password to keep. Run this without "
                        "--keep-password to create one.",
                        file=sys.stderr,
                    )
                    return 1
                account = Mentor(
                    full_name=ADMIN_NAME,
                    email=email,
                    password_hash=security.hash_password(password),
                    is_admin=True,
                    # An administrator account is not a mentor the platform
                    # has checked the identity of, and it is not a
                    # demonstration row either. Both flags stay false so the
                    # directory and the demonstration reset leave it alone.
                    verified=False,
                    is_demo=False,
                )
                session.add(account)
                session.commit()
                session.refresh(account)
                created = True
            else:
                account.is_admin = True
                if not arguments.keep_password:
                    account.password_hash = security.hash_password(password)
                session.commit()
                created = False

            account_id = account.id
    finally:
        engine.dispose()

    print(
        f"Created administrator account {account_id}."
        if created
        else f"Account {account_id} is now an administrator."
    )
    print(f"  address: {email}")
    if arguments.keep_password:
        print("  password: unchanged")
    elif generated:
        # Printed once, because only the hash is stored. There is nothing to
        # recover it from later: a lost password means running this again.
        print(f"  password: {password}")
        print("")
        print(
            f"That password was generated by this run and is shown once. Only "
            f"its hash is stored, so write it down now. Set "
            f"{PASSWORD_VARIABLE} to choose your own instead."
        )
    else:
        print(f"  password: as set in {PASSWORD_VARIABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Mark one mentor as verified, or take it back.

Verification is the platform's own statement about a mentor: somebody checked
who they are. Nothing a mentor sends can set it, which is why there is no
endpoint for it and why this is a script run by whoever did the checking.

Two things change together, and that is the point of doing it here rather than
with an UPDATE by hand:

* ``mentors.verified`` is what the public directory shows as a checkmark.
* ``services.profile_verified`` on each of that mentor's services is the same
  claim in the form the model reads, and it is one of the eight inputs behind
  a price.

Leaving the two to disagree would mean a mentor displayed with a checkmark
whose price was worked out as though nobody had checked them, or the reverse.
So both move, and the script says what the prices of the affected services
would be next time they are asked for, rather than silently repricing
anything: a price is advice the mentor answers, so this script does not issue
new advice on their behalf.

Run from the project root, against the database ``DATABASE_URL`` points at:

    python scripts/verify_mentor.py mentor@example.com
    python scripts/verify_mentor.py mentor@example.com --revoke

The address is matched without regard to capitals, the same way signing in
matches it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db import Mentor, create_db_engine  # noqa: E402
from src.mentor.security import normalise_email  # noqa: E402


def find_mentor(session: Session, email: str) -> Mentor | None:
    """The account registered to one address, matched without case."""
    return session.scalar(
        select(Mentor).where(func.lower(Mentor.email) == normalise_email(email))
    )


def set_verified(mentor: Mentor, verified: bool) -> int:
    """
    Set the flag on the mentor and on every service they offer.

    Returns how many services changed, so the caller can report what the
    next price for each of them will be worked out from.
    """
    mentor.verified = verified
    changed = 0
    for service in mentor.services:
        if bool(service.profile_verified) != verified:
            service.profile_verified = verified
            changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mark a mentor as verified, so the checkmark on their public "
            "profile can be demonstrated, or take the verification back."
        )
    )
    parser.add_argument("email", help="the address the mentor signs in with")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="clear the verification instead of setting it",
    )
    arguments = parser.parse_args(argv)
    verified = not arguments.revoke

    engine = create_db_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            mentor = find_mentor(session, arguments.email)
            if mentor is None:
                print(
                    "FAILED: no mentor is registered with that address.",
                    file=sys.stderr,
                )
                return 1
            was = bool(mentor.verified)
            changed = set_verified(mentor, verified)
            session.commit()
    finally:
        engine.dispose()

    state = "verified" if verified else "not verified"
    if was == verified:
        print(f"Mentor {mentor.id} was already {state}.")
    else:
        print(f"Mentor {mentor.id} is now {state}.")
    if changed:
        print(
            f"{changed} service(s) now carry the same answer, so the next "
            f"price asked for each of them is worked out from it. Existing "
            f"prices are unchanged: the mentor answered those."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

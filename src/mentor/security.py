"""
Passwords and access tokens: the two secrets the API handles.

Everything here is deliberately small and deliberately in one place. A mentor
proves who they are by sending a password once, and afterwards by sending a
token that says the server already checked it. Those are the only two secrets
in the system, so the hashing, the verification, the signing and the reading
back all live in this module and nothing else performs any of them.

Three decisions worth knowing about:

**Passwords are hashed with Argon2id.** It is the current recommendation of
the Password Hashing Competition and the default of ``argon2-cffi``, which
supplies the parameters. A hash is deliberately slow to compute, which is
useless against a legitimate login and expensive against someone working
through a stolen table of them.

**An unknown email is verified against a dummy hash.** A login that returned
immediately for an address nobody has registered, and a tenth of a second
later for one that exists, would answer "is this person on the platform"
without being asked. So the unknown case does the same work as the known one
and discards the result. :data:`DUMMY_HASH` exists for that and for nothing
else: no password hashes to it.

**Tokens are signed, not stored.** A token carries the mentor's id and an
expiry, and a signature over both. The server keeps no session table, so
nothing has to be looked up to decide whether a request is authentic, and
there is nothing to clean up when it expires. The cost of that is the one
property a stateless token cannot have: it cannot be revoked before it
expires, which is why the expiry is seven days rather than a year. Logging out
is therefore the client discarding the token, which is all it can be.

The signing key comes from ``SECRET_KEY``. In production a missing or short
key stops the application from starting, because the alternative is a server
that issues tokens anyone can forge while looking perfectly healthy. In
development a key is generated at startup and one warning line says so: the
tokens issued before a restart stop working after it, which is the correct
inconvenience for a key nobody chose.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from dotenv import load_dotenv

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

ENV_FILE = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
# Eight characters is the floor NIST SP 800-63B sets for a user-chosen
# password. The ceiling is not a rule about passwords but a guard about
# hashing: Argon2 reads the whole input, so an unbounded one is an unbounded
# amount of work for the server to do on request.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

EMAIL_MAX_LENGTH = 320

PASSWORD_LENGTH_MESSAGE = (
    f"Choose a password between {PASSWORD_MIN_LENGTH} and "
    f"{PASSWORD_MAX_LENGTH} characters."
)

PASSWORD_BLANK_MESSAGE = "Enter a password."

# One hasher, with the library's defaults. The parameters are part of the
# stored hash, so a future change to them does not invalidate the hashes
# written before it: an old hash still verifies and can be rewritten.
_hasher = PasswordHasher()

# What an unknown email is checked against, so that the work done is the same
# either way. Hashed from a random value that is thrown away, so this hash has
# no password at all.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


class PasswordError(ValueError):
    """
    The password cannot be used, with a sentence written for the mentor.

    A ``ValueError`` so that a Pydantic validator raising it produces the
    message as a field error, the same way every other answer on the
    registration form does.
    """


def normalise_email(value: Any) -> str:
    """
    One address, in the single form the system stores and compares.

    Trimmed and lowercased. The domain half of an address is
    case-insensitive by definition and no mail provider in practice treats the
    local half as significant, so two mentors typing the same address with
    different capitals are the same mentor, and the unique index on the
    lowercased column is what makes that true rather than merely intended.
    """
    return str(value).strip().lower()


def validate_password(value: Any) -> str:
    """
    A password as typed, checked for length and nothing else.

    No composition rules. A requirement for a digit and a capital is known to
    push people towards a short password with a digit and a capital on the
    end, and the length floor is the part that carries the weight. The value
    is not stripped: leading and trailing spaces are characters a mentor chose
    and removing them would change their password without telling them.
    """
    if not isinstance(value, str) or not value:
        raise PasswordError(PASSWORD_BLANK_MESSAGE)
    if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
        raise PasswordError(PASSWORD_LENGTH_MESSAGE)
    return value


def hash_password(password: str) -> str:
    """The stored form of one password. Never reversible, never logged."""
    return _hasher.hash(validate_password(password))


def verify_password(password: Any, password_hash: str | None) -> bool:
    """
    Whether ``password`` is the one behind ``password_hash``.

    Never short-circuits. A blank password and a missing hash are both real
    cases rather than programming errors: the column is nullable, so a mentor
    row written before this module existed has no password at all. Both are
    checked against :data:`DUMMY_HASH` and refused, so every refusal costs the
    same as a wrong password rather than returning in no time at all.
    """
    candidate = password if isinstance(password, str) and password else NO_PASSWORD
    try:
        return _hasher.verify(password_hash or DUMMY_HASH, candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Stood in for a password that was not sent, so the verification above runs
# and fails rather than being skipped. It cannot be anyone's password: a
# password that short is refused by validate_password before it is ever
# hashed.
NO_PASSWORD = "\x00"


# ---------------------------------------------------------------------------
# The signing key
# ---------------------------------------------------------------------------
SECRET_KEY_VARIABLE = "SECRET_KEY"
ENVIRONMENT_VARIABLE = "ENVIRONMENT"

PRODUCTION = "production"

# Thirty-two characters of a random key is 256 bits, which is the size of the
# HMAC-SHA256 output the signature is. A shorter key does not make the
# signature shorter, it makes it cheaper to search for.
SECRET_KEY_MIN_LENGTH = 32

MISSING_SECRET_MESSAGE = (
    f"{SECRET_KEY_VARIABLE} is not set, and this is a "
    f"{PRODUCTION} environment. Access tokens are signed with it, so without "
    f"one the server would issue tokens that anyone could forge. Set "
    f"{SECRET_KEY_VARIABLE} to at least {SECRET_KEY_MIN_LENGTH} random "
    f"characters and start again."
)

SHORT_SECRET_MESSAGE = (
    f"{SECRET_KEY_VARIABLE} is shorter than {SECRET_KEY_MIN_LENGTH} "
    f"characters, and this is a {PRODUCTION} environment. Set it to at least "
    f"{SECRET_KEY_MIN_LENGTH} random characters and start again."
)

GENERATED_SECRET_WARNING = (
    "%s is not set, so a random signing key was generated for this process. "
    "Access tokens stop working when it restarts. Set %s in the environment "
    "to keep them valid, and note that a %s environment refuses to start "
    "without one."
)


class InsecureConfigurationError(RuntimeError):
    """
    The server is configured in a way that cannot be served safely.

    Raised at startup rather than at the first request. A deployment that is
    missing its signing key has a fault an operator has to fix, and the worst
    possible response to it is a server that answers normally while handing
    out forgeable tokens.
    """


_secret_key: str | None = None


def environment(value: str | None = None) -> str:
    """
    Which environment this process believes it is running in.

    Read from ``ENVIRONMENT``, lowercased and trimmed, and empty when unset.
    Only one value has any effect: :data:`PRODUCTION`, which turns the missing
    key from a warning into a refusal to start.
    """
    raw = os.environ.get(ENVIRONMENT_VARIABLE) if value is None else value
    return (raw or "").strip().lower()


def secret_key_for(environment_name: str, secret: str | None) -> str:
    """
    The key to sign with, given an environment and whatever was configured.

    The whole rule, with nothing read from anywhere, so it can be stated and
    tested as the rule it is. Neither the key nor any part of it is ever
    logged or returned in a response: the only thing said out loud is that one
    was generated.
    """
    name = (environment_name or "").strip().lower()
    key = (secret or "").strip()

    if name == PRODUCTION:
        if not key:
            raise InsecureConfigurationError(MISSING_SECRET_MESSAGE)
        if len(key) < SECRET_KEY_MIN_LENGTH:
            raise InsecureConfigurationError(SHORT_SECRET_MESSAGE)
        return key

    if key:
        return key

    logger.warning(
        GENERATED_SECRET_WARNING, SECRET_KEY_VARIABLE, SECRET_KEY_VARIABLE, PRODUCTION
    )
    return secrets.token_urlsafe(SECRET_KEY_MIN_LENGTH)


def resolve_secret_key() -> str:
    """
    The key tokens are signed with, read from the environment or ``.env``.

    ``.env`` is loaded the same way the database URL is, with ``override``
    off, so the real environment always wins. The file is never written and
    nothing from it is printed.
    """
    load_dotenv(ENV_FILE, override=False)
    return secret_key_for(environment(), os.environ.get(SECRET_KEY_VARIABLE))


def get_secret_key() -> str:
    """
    The signing key for this process, resolved once.

    Cached because a development key is generated: resolving it per call would
    sign every token with a different key and verify none of them.
    """
    global _secret_key
    if _secret_key is None:
        _secret_key = resolve_secret_key()
    return _secret_key


def reset_secret_key() -> None:
    """Forget the cached key, so the next use resolves it again. For tests."""
    global _secret_key
    _secret_key = None


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------
ALGORITHM = "HS256"

# Seven days. Long enough that a mentor is not asked to sign in again while
# they are using the platform, and short enough to bound the one thing a
# stateless token cannot do, which is stop working before it expires.
TOKEN_TTL = timedelta(days=7)

TOKEN_TYPE = "bearer"

AUTH_HEADER = "Authorization"
BEARER_PREFIX = "bearer"

# One message for every way a token can fail to prove anything: absent,
# malformed, signed with another key, expired, or carrying something that is
# not a mentor id. Which of those it was is of no use to the mentor, whose
# only action is the same in all five cases, and of some use to anyone trying
# them one at a time.
INVALID_TOKEN_MESSAGE = "Sign in to continue."

MISSING_TOKEN_MESSAGE = "Sign in to continue."


class TokenError(ValueError):
    """A token did not prove who the caller is."""


def create_access_token(
    mentor_id: int, *, issued_at: datetime | None = None, ttl: timedelta | None = None
) -> str:
    """
    A signed token saying which mentor the bearer is.

    The subject is the mentor's id as a string, which is what the JWT
    specification requires of that claim, and is read back as an integer. The
    issue time is carried as well as the expiry so a token can be described
    without being trusted.
    """
    now = issued_at or datetime.now(UTC)
    payload = {
        "sub": str(int(mentor_id)),
        "iat": int(now.timestamp()),
        "exp": int((now + (ttl or TOKEN_TTL)).timestamp()),
    }
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)


def token_lifetime_seconds(ttl: timedelta | None = None) -> int:
    """How long a freshly issued token lasts, in whole seconds."""
    return int((ttl or TOKEN_TTL).total_seconds())


def read_access_token(token: Any) -> int:
    """
    The mentor id a token proves, or :class:`TokenError`.

    The signature and the expiry are both checked by the library, which is the
    point of using one: an implementation that decoded the payload and then
    compared the expiry itself would accept an unsigned token with a
    favourable one in it.
    """
    if not isinstance(token, str) or not token.strip():
        raise TokenError(MISSING_TOKEN_MESSAGE)
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise TokenError(INVALID_TOKEN_MESSAGE) from error

    try:
        mentor_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as error:
        raise TokenError(INVALID_TOKEN_MESSAGE) from error
    if mentor_id < 1:
        raise TokenError(INVALID_TOKEN_MESSAGE)
    return mentor_id


def bearer_token(header_value: str | None) -> str:
    """
    The token out of an ``Authorization`` header value.

    The scheme is compared without case, because the specification says it is
    case-insensitive and clients disagree about it in practice.
    """
    if header_value is None or not header_value.strip():
        raise TokenError(MISSING_TOKEN_MESSAGE)
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != BEARER_PREFIX:
        raise TokenError(INVALID_TOKEN_MESSAGE)
    token = parts[1].strip()
    if not token:
        raise TokenError(INVALID_TOKEN_MESSAGE)
    return token

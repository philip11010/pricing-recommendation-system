"""
Who is calling: the one function that decides whose data a request may see.

A mentor signs in once and is given a signed access token. Every mentor-scoped
request carries it in an ``Authorization: Bearer`` header, and
:func:`get_current_mentor_id` is the only thing in the codebase that turns
that header into a mentor id. Every mentor-scoped endpoint depends on it, and
none of them reads an identity from the request itself, which is what kept
replacing the prototype's trusted header with a real token check a change to
this module and nothing else.

The matching discipline is in the endpoints and is unchanged: a query is
always filtered by the id this returns, never checked against it afterwards. A
mentor asking for someone else's service gets 404, not 403, because 403 would
confirm that the row exists.

There are no cookies. The token is read from a header the frontend sets, so a
request from a browser carries no credentials of its own and nothing can be
sent by a page the mentor did not open deliberately. Signing out is the client
discarding the token: the server keeps no session to end.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.mentor.security import (
    AUTH_HEADER,
    MISSING_TOKEN_MESSAGE,
    TokenError,
    bearer_token,
    read_access_token,
)

# Sent on a 401 so a client knows which scheme to retry with, which is what
# the status code means rather than merely suggests.
UNAUTHORIZED_HEADERS: dict[str, str] = {"WWW-Authenticate": "Bearer"}

AUTH_HEADER_DESCRIPTION = (
    "The access token from /auth/login or /auth/register, sent as " "`Bearer <token>`."
)


def unauthorized(message: str = MISSING_TOKEN_MESSAGE) -> HTTPException:
    """One 401, with the scheme named, however the token failed."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers=dict(UNAUTHORIZED_HEADERS),
    )


def get_current_mentor_id(
    authorization: str | None = Header(
        default=None,
        alias=AUTH_HEADER,
        description=AUTH_HEADER_DESCRIPTION,
    ),
) -> int:
    """
    The mentor this request is made by, proved by the token it carries.

    Every failure answers with the same sentence: no header, a header in
    another scheme, a token signed with a different key, an expired one, or
    one carrying something that is not a mentor id. The mentor's next action
    is the same in all five cases, and telling a caller which of them it was
    would let them be tried one at a time.
    """
    try:
        return read_access_token(bearer_token(authorization))
    except TokenError as error:
        raise unauthorized(str(error)) from None

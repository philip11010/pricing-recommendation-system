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

One more question is answered here, and only here: whether the caller may read
the operations dashboard. :func:`require_admin` is the single gate on every
/admin endpoint, and it is the one place in the codebase where a refusal is
403 rather than 404. The rest of the API answers 404 for a record that is not
the caller's, because the alternative would confirm that somebody else's
record exists. /admin is different in kind: it is one fixed set of paths that
everybody knows exists, nothing about it is per account, and there is nothing
for a 403 to disclose. Saying "you are signed in and not allowed here" is the
accurate answer, and it is the one that stops a frontend retrying the sign in.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from src.db import get_session
from src.db.mentor_models import Mentor
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

# What an account that is not an administrator is told. It names no address
# and no account: the caller already knows who they are, and the sentence is
# the same for every signed-in caller who is not allowed here.
NOT_ADMIN_MESSAGE = "This account cannot read the administration pages."


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


def signed_in_mentor(
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> Mentor:
    """
    The mentor the token belongs to, or 401.

    A token that is perfectly valid but names a mentor who no longer exists is
    not a request for a missing record: it is an identity that cannot be
    established, which is what 401 means. That is the one case where a signed
    request answers 401 rather than 404.
    """
    mentor = session.get(Mentor, current_mentor_id)
    if mentor is None:
        raise unauthorized()
    return mentor


def require_admin(mentor: Mentor = Depends(signed_in_mentor)) -> Mentor:
    """
    The administrator this request belongs to, or 401, or 403.

    The two refusals are different answers to different questions, and the
    difference is what a frontend acts on:

    * **401** when there is no usable token at all, which is what
      :func:`get_current_mentor_id` and :func:`signed_in_mentor` already
      raise. The caller should sign in.
    * **403** when the token is good and the account is not an administrator.
      The caller is signed in and signing in again would change nothing.

    Read from the account on every request rather than carried in the token,
    so that revoking the flag takes effect on the next call instead of when
    the token happens to expire. One database read per admin request, on a
    page nobody loads in a loop.
    """
    if not bool(mentor.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=NOT_ADMIN_MESSAGE
        )
    return mentor

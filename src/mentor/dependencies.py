"""
Who is calling, and the one place that will become real authentication.

There is no authentication yet. The caller states who they are in an
``X-Mentor-Id`` header and the API believes them, which is fine for a
prototype on a developer's machine and would not be fine anywhere else.

What makes that safe to build on is that the trust lives in exactly one
function. :func:`get_current_mentor_id` is the only thing in the codebase that
decides whose data a request may see, and every mentor-scoped endpoint depends
on it. Replacing it with a token check is therefore a change to this function
and nothing else: no endpoint has to be revisited, because none of them reads
an id from the request themselves.

The matching discipline is in the endpoints: a query is always filtered by the
id this returns, never checked against it afterwards. A mentor asking for
someone else's service gets 404, not 403, because 403 would confirm that the
row exists.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

MENTOR_ID_HEADER = "X-Mentor-Id"

MISSING_IDENTITY_MESSAGE = (
    f"This request has to say which mentor it is for. Send the mentor's id in "
    f"the {MENTOR_ID_HEADER} header."
)

INVALID_IDENTITY_MESSAGE = (
    f"The {MENTOR_ID_HEADER} header must be a mentor id, which is a positive "
    f"whole number."
)


def get_current_mentor_id(
    x_mentor_id: str | None = Header(
        default=None,
        alias=MENTOR_ID_HEADER,
        description=(
            "The id of the mentor making the request. A placeholder for "
            "authentication, which this prototype does not have yet."
        ),
    ),
) -> int:
    """
    The mentor this request is acting as.

    Declared as a string and converted here rather than as an ``int`` header,
    so a non-numeric value produces the message above instead of FastAPI's own
    validation document.
    """
    if x_mentor_id is None or not x_mentor_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MISSING_IDENTITY_MESSAGE,
        )
    try:
        mentor_id = int(x_mentor_id.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_IDENTITY_MESSAGE,
        ) from None
    if mentor_id < 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_IDENTITY_MESSAGE,
        )
    return mentor_id

from datetime import date

from fastapi import HTTPException, Query, status


def date_range(
    from_: date | None = Query(default=None, alias="from", description="Inclusive start date"),
    to: date | None = Query(default=None, description="Inclusive end date"),
) -> tuple[date | None, date | None]:
    if from_ and to and from_ > to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "'from' must be on or before 'to'"
        )
    return from_, to

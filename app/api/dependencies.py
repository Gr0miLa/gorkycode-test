from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException


async def get_session_id(x_session_id: Annotated[str, Header()]) -> str:
    try:
        return str(UUID(x_session_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный X-Session-ID") from exc


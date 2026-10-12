from typing import Literal

from pydantic import BaseModel, Field


class DBHealthResponse(BaseModel):
    status: Literal["ok"] = Field(..., description="Database health status.")
    database: Literal["connected"] = Field(
        ...,
        description="Database connectivity indicator.",
    )

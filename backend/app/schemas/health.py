from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(..., description="Application health state.")
    service: Literal["document-intelligence-api"] = Field(
        ...,
        description="Service name reported by the backend.",
    )

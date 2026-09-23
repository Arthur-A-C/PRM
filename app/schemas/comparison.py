import uuid

from pydantic import BaseModel, Field


class ComparisonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    offer_ids: list[uuid.UUID] = Field(min_length=2, max_length=4)
    reference_offer_id: uuid.UUID | None = None

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    customer_ref: str = Field(min_length=2, max_length=80)
    message: str = Field(min_length=5, max_length=8000)


class ActionDecision(BaseModel):
    action: str = Field(pattern="^(replacement|close_ticket)$")
    approved: bool
    reviewer_note: str = Field(default="", max_length=1000)


class TranslateRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=4000)
    source_locale: str = Field(min_length=2, max_length=16)
    target_locale: str = Field(min_length=2, max_length=16)


class BatchTranslateRequest(BaseModel):
    items: list[TranslateRequest] = Field(min_length=1, max_length=50)


class GlossaryRequest(BaseModel):
    source_term: str = Field(min_length=1, max_length=200)
    target_term: str = Field(min_length=1, max_length=200)
    source_locale: str = Field(min_length=2, max_length=16)
    target_locale: str = Field(min_length=2, max_length=16)

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas._request import RequestModel
from app.schemas.locale import DEFAULT_LOCALE, LocaleCode


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=200)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    preferred_locale: LocaleCode = DEFAULT_LOCALE
    # Whether anyone actually said this. The client needs it to know
    # whether the profile's language outranks the browser's: it does when
    # a person picked it, and it does not when the column simply had to
    # hold a value. See the ``locale_source`` comment on the model.
    locale_source: Literal["default", "detected", "chosen"] = "chosen"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    avatar_url: str | None = None


class PreferredLocaleUpdate(RequestModel):
    """Body for ``PATCH /users/me/preferences``.

    Kept as a dedicated schema so we can grow it (timezone, theme, …) without
    breaking the existing endpoint contract.

    ``detected`` marks the call as the client reporting what the browser
    asked for, not a person picking from a menu. The two must not be
    confused: a detected value may be replaced by a better signal later,
    while a chosen one is never overwritten by anything automatic. It
    defaults to False so the language switcher — the original and still
    the main caller — keeps recording real choices without change.
    """

    preferred_locale: LocaleCode
    detected: bool = False

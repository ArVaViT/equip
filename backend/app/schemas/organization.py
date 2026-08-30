"""Request and response shapes for administering an organization.

Creation is platform staff's, deliberately: admission is a human
decision, not a signup form. See
``product/decisions/admission-organizations-and-teachers.md``.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._request import RequestModel
from app.schemas.course import CourseSummary

#: Lowercase letters, digits and single hyphens between them. The same
#: shape Postgres enforces with a regex CHECK; declared here too so a
#: bad slug is refused before it reaches the database, and so the error
#: names the field rather than the constraint.
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

OrganizationStatus = Literal["pending", "approved", "verified", "suspended"]


class OrganizationCreate(RequestModel):
    slug: str = Field(..., min_length=2, max_length=63, pattern=SLUG_PATTERN)
    public_name: str = Field(..., min_length=2, max_length=200)
    legal_name: str | None = Field(None, max_length=200)
    country: str | None = Field(None, min_length=2, max_length=2)
    #: An organization created by staff is ``approved``: somebody decided
    #: to admit it. ``pending`` exists for a future application flow and
    #: can be set explicitly.
    status: OrganizationStatus = "approved"


class OrganizationUpdate(RequestModel):
    """Everything an organization can be edited into — except its slug.

    The slug is in the URL of the organization's page and printed on
    every certificate it has issued. Changing it turns a diploma into a
    document pointing at nothing, so it is not editable here at all
    rather than editable-until-the-first-certificate: a rule that only
    sometimes applies is a rule somebody eventually gets wrong.
    """

    public_name: str | None = Field(None, min_length=2, max_length=200)
    legal_name: str | None = Field(None, max_length=200)
    country: str | None = Field(None, min_length=2, max_length=2)
    status: OrganizationStatus | None = None
    verification_basis: str | None = Field(None, max_length=500)


class DirectorAppointment(RequestModel):
    """Who runs this organization.

    By email rather than by id: the person appointing a director knows
    the address they wrote to, and looking up an id first is a step that
    exists only to make the API tidier for the machine.
    """

    email: str = Field(..., min_length=3, max_length=320)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    public_name: str
    legal_name: str | None = None
    country: str | None = None
    status: str
    verification_basis: str | None = None
    verified_at: datetime | None = None
    created_at: datetime
    #: Filled by the route, not by the ORM: how many people belong here
    #: and who runs it are the two questions the admin panel asks first.
    member_count: int = 0
    director_emails: list[str] = []


class OrganizationPublicResponse(BaseModel):
    """What a stranger sees at ``/s/<slug>``.

    Deliberately narrow: a name, a country, whether the organization is
    still active, and its public courses. No member counts, no director
    emails, no internal status string — the page is read by people who
    followed a link off a certificate, and everything beyond "is this
    school real and what does it teach" is the organization's business.

    ``active`` rather than the raw status, because ``pending`` and
    ``approved`` are admission bookkeeping and mean nothing to a reader;
    what matters outside is whether courses are being served. ``verified``
    is separate because it is the claim the platform itself stands behind.
    """

    slug: str
    public_name: str
    country: str | None = None
    active: bool
    verified: bool
    courses: list[CourseSummary] = []

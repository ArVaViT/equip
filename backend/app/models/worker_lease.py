"""A named lease on background work that must not run twice at once.

See ``app/services/worker_lease.py`` and
``supabase/migrations/20261001160000_worker_leases.sql`` for why this is a
row and not an advisory lock.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkerLease(Base):
    __tablename__ = "worker_leases"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    holder: Mapped[uuid.UUID] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

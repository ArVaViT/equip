"""Whether a file named in a submission is one the student actually uploaded.

The bucket's INSERT policy keeps a student inside their own folder, but the
row that hands the work in is written by the API. Two things are asked of
the key before the row is written:

* its exact shape, the one the client builds and nothing else
  (``<course>/<assignment>/<student>/<13-digit ms>-<safe name>``). A prefix
  test let through ``%2e%2e`` and similar spellings that a browser folds
  into ``..`` when the teacher's client signs the URL, pointing the
  teacher at another student's file;
* that the object exists now and was uploaded by this student. Without it
  a student could hand in a key on time and upload the file to it after
  the deadline, or hand in a spelling of a key the delete policy does not
  recognise and replace the file after handing it in.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: What ``sanitizeFileName`` in frontend/src/services/storage.ts produces,
#: after ``Date.now()`` and a dash. Nothing outside it is a key the client
#: ever writes.
_FILE_SEGMENT = r"\d{13}-[A-Za-z0-9._()-]{1,100}"


def key_is_in_own_folder(path: str, *, course_id: str, assignment_id: str, student_id: str) -> bool:
    folder = "/".join(re.escape(part) for part in (course_id, assignment_id, student_id))
    return re.fullmatch(f"{folder}/{_FILE_SEGMENT}", path) is not None


def uploaded_by(db: Session, *, bucket: str, path: str) -> str | None:
    """The uploader of ``bucket/path``, or None when no such object exists."""
    row = db.execute(
        text("SELECT owner_id FROM storage.objects WHERE bucket_id = :bucket AND name = :path"),
        {"bucket": bucket, "path": path},
    ).first()
    return None if row is None else row[0]

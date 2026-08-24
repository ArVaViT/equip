"""Base class for every schema that models a request body.

Pydantic ignores unknown keys by default. For a response that is the
right call — a client sending back more than it was given costs nothing.
For a request it is data loss with a 200 on it: a caller that misspells
``text_answer`` as ``answer_text`` gets the same success envelope as one
that spelled it right, and the essay it carried is gone. The endpoint
never sees a field, so it cannot complain about one.

That exact case was live. ``POST /quizzes/{id}/submit`` accepted an essay
under the wrong key, stored ``NULL`` for the answer, marked the question
wrong, and never queued it for the teacher — the student's work vanished
between their browser and the grading queue, silently, on both sides.

So request schemas reject what they do not recognise. A typo becomes a
422 naming the offending field, which is the difference between a bug the
caller can see and one only the database remembers.

Response schemas keep the permissive default: they are built from ORM
objects, where an unexpected attribute means the model grew a column, not
that a caller made a mistake.
"""

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """A schema parsed from a client-supplied body. Unknown keys are errors."""

    model_config = ConfigDict(extra="forbid")

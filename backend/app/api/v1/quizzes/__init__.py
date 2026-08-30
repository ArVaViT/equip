"""Quiz API package.

The router from ``_router.py`` is exposed as ``router`` so callers can
keep doing ``from app.api.v1 import quizzes`` /
``quizzes.router`` as before.

Importing the sub-modules is done purely for their side effects:
each one registers its endpoints on the shared router.
"""

# Side-effect imports register endpoints on the shared ``router``.
from . import attempts as _attempts  # noqa: F401
from . import crud as _crud  # noqa: F401
from . import extra as _extra  # noqa: F401
from . import grading as _grading  # noqa: F401
from . import questions as _questions  # noqa: F401
from ._router import router

__all__ = ["router"]

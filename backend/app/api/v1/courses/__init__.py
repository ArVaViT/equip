"""Courses API package.

The router from ``_router.py`` is exposed as ``router`` so existing
callers can keep doing ``from app.api.v1 import courses`` /
``courses.router``.

The endpoint modules are imported purely for their side effects: each
one registers its routes on the shared router.
"""

# Side-effect imports register endpoints on the shared ``router``.
from . import catalog as _catalog  # noqa: F401
from . import chapters as _chapters  # noqa: F401
from . import crud as _crud  # noqa: F401
from . import enrollment as _enrollment  # noqa: F401
from . import modules as _modules  # noqa: F401
from . import readiness as _readiness  # noqa: F401
from . import translate as _translate  # noqa: F401
from ._router import router

__all__ = ["router"]

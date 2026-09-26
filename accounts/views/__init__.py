"""accounts.views, split by audience.

Was one 6600+ line file; now one module per audience so a change to
the MEI self-service screens does not require scrolling past the
internal back-office views to get there. See
docs/EMPRESA_HORACERTA_ORGANIZACAO.md for the rationale.

- _shared: imports, constants and helpers used by more than one audience.
- auth: signup/login/logout and the generic role-based dashboard redirect.
- internal: staff-only back office (interno/...).
- company: the empresa-facing screens (empresa/...).
- mei: the prestador/MEI self-service screens (me/...).
- public: unauthenticated pages (landing, terms, public report links).
"""
from ._shared import *  # noqa: F401,F403
from .auth import *  # noqa: F401,F403
from .internal import *  # noqa: F401,F403
from .company import *  # noqa: F401,F403
from .mei import *  # noqa: F401,F403
from .public import *  # noqa: F401,F403

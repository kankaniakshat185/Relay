"""Import every model module once, purely for the side effect of
registering its table(s) on `Base.metadata` (`core/db.py`).

Nothing in this codebase imports every model module implicitly — each
one only gets pulled in by whatever feature actually uses it directly.
That's fine for FastAPI's own process (`main.py` imports every feature's
router, which transitively imports every model), but the Celery worker
process (`celery -A relay_api.jobs.celery_app worker ...`) only imports
`jobs/celery_app.py` and whatever `jobs/*.py` needs directly — which
never touches `auth.models` or `features/notes/models.py`, for two
concrete examples.

Found live: `ConnectorCredential.user_id` declares `ForeignKey("users.id")`
as a string — SQLAlchemy only resolves that against a real `users` Table
object if `auth.models` (where `User`/`users` is defined) has been
imported into *this process's* `Base.metadata` already. It hadn't, in the
worker — every real indexing run failed at `db.commit()` with
`NoReferencedTableError: ... could not find table 'users'`, immediately
after a completely unrelated fix (the Redis TLS config) let `.delay()`
calls succeed for the first time, so this pre-existing gap had simply
never been exercised in production before.

`alembic/env.py` already had to solve the exact same problem for
autogenerate to see every table — this module is that same import list,
factored out once so the two don't drift against each other again.
"""

from relay_api.auth import models as _auth_models  # noqa: F401
from relay_api.connectors import models as _connector_models  # noqa: F401
from relay_api.engine.ingestion import models as _ingestion_models  # noqa: F401
from relay_api.features.flaky_tests import models as _flaky_tests_models  # noqa: F401
from relay_api.features.notes import models as _notes_models  # noqa: F401

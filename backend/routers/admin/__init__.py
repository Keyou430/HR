"""Admin routers package.

To migrate incrementally: move endpoint groups from ``admin_router.py``
into dedicated modules here, then re-export via this package.

Current structure::

    _shared.py   – common helpers, SQL fragments, org-scoping utilities

The single ``router`` from ``admin_router`` is still the primary export
for backward compatibility.
"""

from admin_router import router  # noqa: F401 – backward-compatible export

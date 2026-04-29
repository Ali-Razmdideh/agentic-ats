"""Base repository — every tenant-scoped table goes through this."""

from __future__ import annotations

from typing import ClassVar, Generic, TypeVar

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import Base

M = TypeVar("M", bound=Base)


class OrgScopedRepository(Generic[M]):
    """Repository that injects ``WHERE org_id = :org_id`` on every query.

    Subclasses set ``Model`` and use ``self._scope(stmt)`` for selects/
    updates/deletes, and ``self._stamp(model_kwargs)`` to add ``org_id``
    on inserts.

    The class-level ``__leak_test__`` guard is checked by a pytest collection
    hook; every concrete subclass must opt in by setting it to True after
    the per-repo tenant-leak test is in place.
    """

    Model: ClassVar[type[Base]]
    __leak_test__: ClassVar[bool] = False

    def __init__(self, session: AsyncSession, org_id: int) -> None:
        self._session = session
        self._org_id = org_id

    @property
    def org_id(self) -> int:
        return self._org_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    def _scope(self, stmt: Select) -> Select:  # type: ignore[type-arg]
        return stmt.where(
            self.Model.org_id == self._org_id  # type: ignore[attr-defined]
        )

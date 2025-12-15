"""Base repository with common CRUD operations.

Provides a generic async repository pattern for SQLAlchemy models.
"""

from typing import Any, Generic, TypeVar, Sequence
from datetime import datetime

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic async repository with common CRUD operations.

    Provides standard database operations for SQLAlchemy models:
    - get_by_id: Retrieve single record by primary key
    - get_all: Retrieve all records with optional pagination
    - get_by_filter: Retrieve records matching filter criteria
    - create: Insert new record
    - update: Update existing record
    - delete: Remove record
    - count: Count records matching criteria
    - exists: Check if record exists

    Example:
        repo = RedemptionRepository(session)
        redemption = await repo.get_by_id(1)
        all_pending = await repo.get_by_filter(status="PENDING")
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with async session.

        @param session - SQLAlchemy async session
        """
        self.session = session

    async def get_by_id(self, id: Any) -> ModelType | None:
        """Get record by primary key.

        @param id - Primary key value
        @returns Model instance or None if not found
        """
        return await self.session.get(self.model, id)

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
    ) -> Sequence[ModelType]:
        """Get all records with pagination.

        @param skip - Number of records to skip (offset)
        @param limit - Maximum number of records to return
        @param order_by - Column to order by (default: primary key desc)
        @returns List of model instances
        """
        stmt = select(self.model)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_filter(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """Get records matching filter criteria.

        @param skip - Number of records to skip
        @param limit - Maximum records to return
        @param order_by - Column to order by
        @param filters - Key-value pairs for filtering (column=value)
        @returns List of matching model instances
        """
        stmt = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_one_by_filter(self, **filters: Any) -> ModelType | None:
        """Get single record matching filter criteria.

        @param filters - Key-value pairs for filtering
        @returns Model instance or None if not found
        """
        stmt = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create(self, obj_in: dict[str, Any] | ModelType) -> ModelType:
        """Create new record.

        @param obj_in - Dictionary or model instance with data
        @returns Created model instance
        """
        if isinstance(obj_in, dict):
            db_obj = self.model(**obj_in)
        else:
            db_obj = obj_in
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def create_many(self, objects: list[dict[str, Any]]) -> list[ModelType]:
        """Create multiple records in batch.

        @param objects - List of dictionaries with data
        @returns List of created model instances
        """
        db_objs = [self.model(**obj) for obj in objects]
        self.session.add_all(db_objs)
        await self.session.flush()
        for obj in db_objs:
            await self.session.refresh(obj)
        return db_objs

    async def update(
        self, id: Any, obj_in: dict[str, Any], *, exclude_unset: bool = True
    ) -> ModelType | None:
        """Update existing record.

        @param id - Primary key of record to update
        @param obj_in - Dictionary with update data
        @param exclude_unset - If True, only update non-None values
        @returns Updated model instance or None if not found
        """
        db_obj = await self.get_by_id(id)
        if db_obj is None:
            return None

        update_data = obj_in
        if exclude_unset:
            update_data = {k: v for k, v in obj_in.items() if v is not None}

        for key, value in update_data.items():
            if hasattr(db_obj, key):
                setattr(db_obj, key, value)

        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def update_by_filter(
        self, values: dict[str, Any], **filters: Any
    ) -> int:
        """Update records matching filter criteria.

        @param values - Dictionary with update values
        @param filters - Key-value pairs for filtering
        @returns Number of updated records
        """
        stmt = update(self.model).values(**values)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete(self, id: Any) -> bool:
        """Delete record by primary key.

        @param id - Primary key of record to delete
        @returns True if deleted, False if not found
        """
        db_obj = await self.get_by_id(id)
        if db_obj is None:
            return False
        await self.session.delete(db_obj)
        await self.session.flush()
        return True

    async def delete_by_filter(self, **filters: Any) -> int:
        """Delete records matching filter criteria.

        @param filters - Key-value pairs for filtering
        @returns Number of deleted records
        """
        stmt = delete(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count(self, **filters: Any) -> int:
        """Count records matching criteria.

        @param filters - Key-value pairs for filtering
        @returns Number of matching records
        """
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def exists(self, **filters: Any) -> bool:
        """Check if record exists matching criteria.

        @param filters - Key-value pairs for filtering
        @returns True if exists, False otherwise
        """
        count = await self.count(**filters)
        return count > 0

    def _build_query(self) -> Select:
        """Build base select query. Override in subclass for joins.

        @returns SQLAlchemy Select statement
        """
        return select(self.model)

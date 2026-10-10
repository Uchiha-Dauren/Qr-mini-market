"""Catalog operations with transaction ownership and atomic stock adjustments."""

from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import BigInteger, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import StockReason
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR
from app.db.transactions import run_write
from app.models import Category, Product, StockMovement
from app.models.catalog import MAX_QUANTITY
from app.schemas.catalog import (
    CategoryCreate,
    CategoryPatch,
    ProductCreate,
    ProductPatch,
    StockAdjustment,
)

T = TypeVar("T")


def active_category_ids(session: Session) -> set[int]:
    """A category is available only while every ancestor is active and acyclic."""
    categories = {row.id: row for row in session.scalars(select(Category))}
    available: set[int] = set()
    for category_id in categories:
        current: int | None = category_id
        seen: set[int] = set()
        while current is not None:
            category = categories.get(current)
            if category is None or not category.is_active or current in seen:
                break
            seen.add(current)
            current = category.parent_id
        else:
            available.add(category_id)
    return available


def product_available(session: Session, product: Product) -> bool:
    return product.is_active and product.category_id in active_category_ids(session)


def category_dict(category: Category, public_ids: dict[int, UUID]) -> dict[str, Any]:
    return {
        "public_id": category.public_id,
        "name": category.name,
        "slug": category.slug,
        "parent_id": public_ids.get(category.parent_id),
        "sort_order": category.sort_order,
        "is_active": category.is_active,
    }


def product_dict(product: Product, category_uuid: UUID, public: bool = False) -> dict[str, Any]:
    if product.price_minor > MAX_SAFE_MINOR:
        raise AppError(422, "AMOUNT_TOO_LARGE", "Цена превышает допустимый предел API.")
    available = product.stock_quantity - product.reserved_quantity
    result = {
        "public_id": product.public_id,
        "name": product.name,
        "barcode": product.barcode,
        "category_id": category_uuid,
        "unit": product.unit,
        "price_minor": product.price_minor,
        "description": product.description,
        "in_stock": product.is_active and available > 0,
    }
    if not public:
        result.update(
            stock_quantity=product.stock_quantity,
            available_quantity=available,
            min_stock_quantity=product.min_stock_quantity,
            is_active=product.is_active,
        )
    return result


class CatalogService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def _write(self, operation: Callable[[Session], T]) -> T:
        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            raise AppError(
                409, "CATALOG_CONFLICT", "Штрихкод или код категории уже используется."
            ) from None

    @staticmethod
    def _category(session: Session, category_uuid: UUID) -> Category:
        category = session.scalar(select(Category).where(Category.public_id == category_uuid))
        if category is None:
            raise AppError(404, "CATEGORY_NOT_FOUND", "Категория не найдена.")
        return category

    @staticmethod
    def _product(session: Session, product_uuid: UUID, lock: bool = False) -> Product:
        if lock:
            session.execute(
                update(Product)
                .where(Product.public_id == product_uuid)
                .values(stock_quantity=Product.stock_quantity)
                .execution_options(synchronize_session=False)
            )
        product = session.scalar(select(Product).where(Product.public_id == product_uuid))
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "Товар не найден.")
        return product

    @staticmethod
    def _lock_tree(session: Session) -> None:
        """Serialize tree changes on a common row before checking ancestors."""
        first_id = select(func.min(Category.id)).scalar_subquery()
        session.execute(
            update(Category).where(Category.id == first_id).values(sort_order=Category.sort_order)
        )

    @staticmethod
    def _check_parent(session: Session, category_id: int, parent_id: int | None) -> None:
        parents = dict(session.execute(select(Category.id, Category.parent_id)).all())
        seen = {category_id}
        while parent_id is not None:
            if parent_id in seen:
                raise AppError(
                    409, "CATEGORY_CYCLE", "Категория не может находиться внутри своего потомка."
                )
            seen.add(parent_id)
            parent_id = parents.get(parent_id)

    @staticmethod
    def _category_result(session: Session, category: Category) -> dict[str, Any]:
        public_ids = dict(session.execute(select(Category.id, Category.public_id)).all())
        return category_dict(category, public_ids)

    @staticmethod
    def _product_result(session: Session, product: Product, public: bool = False) -> dict[str, Any]:
        category_uuid = session.scalar(
            select(Category.public_id).where(Category.id == product.category_id)
        )
        return product_dict(product, category_uuid, public)

    def list_categories(
        self, *, public: bool = False, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Category)
            if public:
                query = query.where(Category.id.in_(active_category_ids(session)))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            categories = session.scalars(
                query.order_by(Category.sort_order, Category.id).limit(limit).offset(offset)
            )
            public_ids = dict(session.execute(select(Category.id, Category.public_id)).all())
            return {
                "items": [category_dict(row, public_ids) for row in categories],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def create_category(self, command: CategoryCreate) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            self._lock_tree(session)
            data = command.model_dump(exclude={"parent_id"})
            parent = self._category(session, command.parent_id) if command.parent_id else None
            category = Category(**data, parent_id=parent.id if parent else None)
            session.add(category)
            session.flush()
            return self._category_result(session, category)

        return self._write(operation)

    def update_category(self, category_uuid: UUID, command: CategoryPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            self._lock_tree(session)
            category = self._category(session, category_uuid)
            data = command.model_dump(exclude_unset=True)
            if "parent_id" in data:
                parent = self._category(session, data["parent_id"]) if data["parent_id"] else None
                data["parent_id"] = parent.id if parent else None
                self._check_parent(session, category.id, data["parent_id"])
            for key, value in data.items():
                setattr(category, key, value)
            session.flush()
            return self._category_result(session, category)

        return self._write(operation)

    def delete_category(self, category_uuid: UUID) -> dict[str, Any]:
        return self.update_category(category_uuid, CategoryPatch(is_active=False))

    def list_products(
        self,
        *,
        q: str | None = None,
        category_id: UUID | None = None,
        include_subcategories: bool = False,
        is_active: bool | None = True,
        barcode: str | None = None,
        limit: int = 50,
        offset: int = 0,
        public: bool = False,
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Product, Category.public_id).join(
                Category, Product.category_id == Category.id
            )
            if q is not None and q.strip():
                query = query.where(
                    Product.name_normalized.contains(q.strip().casefold(), autoescape=True)
                )
            if barcode is not None:
                query = query.where(Product.barcode == barcode)
            if is_active is not None or public:
                query = query.where(Product.is_active.is_(True if public else is_active))
            if public or is_active is True:
                query = query.where(Product.category_id.in_(active_category_ids(session)))
            if category_id is not None:
                category = self._category(session, category_id)
                selected = {category.id}
                if include_subcategories:
                    parents = session.execute(select(Category.id, Category.parent_id)).all()
                    while True:
                        descendants = {row.id for row in parents if row.parent_id in selected}
                        updated = selected | descendants
                        if updated == selected:
                            break
                        selected = updated
                query = query.where(Product.category_id.in_(selected))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.execute(
                query.order_by(Product.name_normalized, Product.id).limit(limit).offset(offset)
            )
            return {
                "items": [product_dict(product, uuid, public) for product, uuid in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def get_product(self, product_uuid: UUID) -> dict[str, Any]:
        with self.factory() as session:
            return self._product_result(session, self._product(session, product_uuid))

    def get_by_barcode(self, barcode: str) -> dict[str, Any]:
        with self.factory() as session:
            product = session.scalar(select(Product).where(Product.barcode == barcode))
            if product is None or not product_available(session, product):
                raise AppError(404, "PRODUCT_NOT_FOUND", "Активный товар не найден.")
            return self._product_result(session, product)

    def create_product(self, command: ProductCreate) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            category = self._category(session, command.category_id)
            product = Product(
                **command.model_dump(exclude={"category_id"}), category_id=category.id
            )
            session.add(product)
            session.flush()
            if product.stock_quantity:
                session.add(
                    StockMovement(
                        product_id=product.id,
                        delta=product.stock_quantity,
                        reason=StockReason.RESTOCK,
                    )
                )
                session.flush()
            return self._product_result(session, product)

        return self._write(operation)

    def update_product(self, product_uuid: UUID, command: ProductPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            product = self._product(session, product_uuid, lock=True)
            data = command.model_dump(exclude_unset=True)
            if "unit" in data and data["unit"] != product.unit:
                raise AppError(
                    409, "UNIT_IMMUTABLE", "Для другой единицы измерения создайте отдельный товар."
                )
            if "category_id" in data:
                data["category_id"] = self._category(session, data["category_id"]).id
            for key, value in data.items():
                setattr(product, key, value)
            session.flush()
            return self._product_result(session, product)

        return self._write(operation)

    def delete_product(self, product_uuid: UUID) -> dict[str, Any]:
        return self.update_product(product_uuid, ProductPatch(is_active=False))

    def adjust_stock(self, product_uuid: UUID, command: StockAdjustment) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            product = self._product(session, product_uuid, lock=True)
            # Widen before arithmetic so PostgreSQL can evaluate the range guard.
            new_stock = cast(Product.stock_quantity, BigInteger) + command.delta
            result = session.execute(
                update(Product)
                .where(
                    Product.id == product.id,
                    new_stock >= Product.reserved_quantity,
                    new_stock <= MAX_QUANTITY,
                )
                .values(stock_quantity=new_stock)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise AppError(
                    409,
                    "STOCK_CONFLICT",
                    "Остаток не может быть меньше резерва или превышать предел.",
                )
            session.add(
                StockMovement(product_id=product.id, delta=command.delta, reason=command.reason)
            )
            session.flush()
            session.refresh(product)
            return self._product_result(session, product)

        return self._write(operation)

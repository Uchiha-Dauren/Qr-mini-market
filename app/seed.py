"""Create deterministic demo catalog entries without resetting existing stock."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.barcodes import generate_internal_ean13
from app.core.config import get_settings
from app.core.enums import ProductUnit, StockReason
from app.db.session import create_db_engine, create_session_factory
from app.db.transactions import run_write
from app.models import Category, Product, StockMovement

# Parent slugs occur before children, so a single pass can resolve the tree.
CATEGORIES = (
    ("food", "Еда", None),
    ("sweets", "Сладости", "food"),
    ("chocolate", "Шоколад", "sweets"),
    ("candy", "Конфеты", "sweets"),
    ("cookies", "Печенье", "sweets"),
    ("dairy", "Молочные продукты", "food"),
    ("milk-kefir", "Молоко и кефир", "dairy"),
    ("cheese-butter", "Сыр и масло", "dairy"),
    ("yogurt-curd", "Йогурты и творог", "dairy"),
    ("produce", "Овощи и фрукты", "food"),
    ("vegetables", "Овощи", "produce"),
    ("fruit", "Фрукты", "produce"),
    ("ready-food", "Готовая еда", "food"),
    ("salads", "Салаты", "ready-food"),
    ("hot-meals", "Горячие блюда", "ready-food"),
    ("baked-goods", "Выпечка", "ready-food"),
    ("bread-dough", "Тесто и хлеб", "food"),
    ("bread", "Хлеб и лаваш", "bread-dough"),
    ("dough", "Тесто и полуфабрикаты", "bread-dough"),
    ("drinks", "Напитки", "food"),
    ("water", "Вода", "drinks"),
    ("juice-soda", "Соки и газировка", "drinks"),
    ("tea-coffee", "Чай и кофе", "drinks"),
    ("household", "Мелочи и товары для дома", None),
    ("stationery", "Канцелярия", "household"),
    ("small-household", "Хозяйственные мелочи", "household"),
    ("hygiene", "Гигиена", "household"),
)

# Prices are whole tenge here and are converted to integer minor units below.
# Quantity and low-stock thresholds are pieces or grams according to the unit.
PRODUCTS = (
    ("Шоколад молочный 90 г", "chocolate", 650, "PIECE", 20, 3),
    ("Шоколад тёмный 85 г", "chocolate", 780, "PIECE", 10, 3),
    ("Конфеты карамель 200 г", "candy", 420, "PIECE", 18, 4),
    ("Конфеты сливочные 150 г", "candy", 550, "PIECE", 2, 4),
    ("Печенье овсяное 300 г", "cookies", 460, "PIECE", 16, 4),
    ("Печенье сахарное 200 г", "cookies", 340, "PIECE", 18, 4),
    ("Молоко 2,5% 1 л", "milk-kefir", 520, "PIECE", 30, 5),
    ("Кефир 2,5% 1 л", "milk-kefir", 570, "PIECE", 12, 3),
    ("Сыр полутвёрдый 200 г", "cheese-butter", 1100, "PIECE", 8, 2),
    ("Масло сливочное 180 г", "cheese-butter", 1200, "PIECE", 10, 2),
    ("Йогурт натуральный 200 г", "yogurt-curd", 380, "PIECE", 20, 4),
    ("Творог 5% 200 г", "yogurt-curd", 650, "PIECE", 12, 3),
    ("Картофель", "vegetables", 220, "KG", 25000, 3000),
    ("Морковь", "vegetables", 240, "KG", 18000, 2500),
    ("Лук репчатый", "vegetables", 190, "KG", 15000, 2000),
    ("Помидоры", "vegetables", 950, "KG", 4000, 1000),
    ("Огурцы", "vegetables", 780, "KG", 500, 1000),
    ("Яблоки", "fruit", 750, "KG", 12000, 2000),
    ("Бананы", "fruit", 980, "KG", 8000, 1500),
    ("Груши", "fruit", 1150, "KG", 6000, 1000),
    ("Апельсины", "fruit", 1050, "KG", 7000, 1000),
    ("Салат овощной 250 г", "salads", 850, "PIECE", 7, 2),
    ("Салат картофельный 250 г", "salads", 790, "PIECE", 1, 2),
    ("Плов с курицей 350 г", "hot-meals", 1450, "PIECE", 8, 2),
    ("Гречка с овощами 300 г", "hot-meals", 990, "PIECE", 6, 2),
    ("Самса с картофелем", "baked-goods", 330, "PIECE", 15, 3),
    ("Булочка с корицей", "baked-goods", 280, "PIECE", 15, 3),
    ("Хлеб пшеничный 500 г", "bread", 250, "PIECE", 24, 5),
    ("Лаваш тонкий 200 г", "bread", 320, "PIECE", 12, 3),
    ("Тесто слоёное 500 г", "dough", 750, "PIECE", 10, 2),
    ("Пельмени с курицей 500 г", "dough", 1300, "PIECE", 8, 2),
    ("Вода питьевая 1,5 л", "water", 230, "PIECE", 40, 8),
    ("Вода газированная 1 л", "water", 270, "PIECE", 24, 5),
    ("Сок яблочный 1 л", "juice-soda", 790, "PIECE", 12, 3),
    ("Лимонад 1 л", "juice-soda", 450, "PIECE", 20, 4),
    ("Чай чёрный 100 г", "tea-coffee", 900, "PIECE", 14, 3),
    ("Кофе растворимый 50 г", "tea-coffee", 1450, "PIECE", 8, 2),
    ("Карандаш простой", "stationery", 100, "PIECE", 25, 5),
    ("Ручка синяя", "stationery", 150, "PIECE", 30, 5),
    ("Тетрадь в клетку 48 листов", "stationery", 270, "PIECE", 20, 4),
    ("Зубочистки деревянные 100 шт", "small-household", 180, "PIECE", 12, 3),
    ("Спички 10 коробков", "small-household", 190, "PIECE", 10, 2),
    ("Пакеты для мусора 30 л", "small-household", 420, "PIECE", 14, 3),
    ("Салфетки бумажные 100 шт", "small-household", 250, "PIECE", 20, 4),
    ("Мыло туалетное 90 г", "hygiene", 290, "PIECE", 18, 3),
    ("Зубная паста 75 мл", "hygiene", 650, "PIECE", 12, 3),
    ("Печенье сезонное 150 г", "cookies", 390, "PIECE", 0, 2),
)


def seed_catalog(factory: sessionmaker[Session]) -> dict[str, int]:
    def operation(session: Session) -> dict[str, int]:
        categories = {item.slug: item for item in session.scalars(select(Category))}
        existing_barcodes = set(session.scalars(select(Product.barcode)))
        created_categories = 0
        created_products = 0
        for sort_order, (slug, name, parent_slug) in enumerate(CATEGORIES):
            if slug in categories:
                continue
            category = Category(
                slug=slug,
                name=name,
                sort_order=sort_order,
                parent_id=categories[parent_slug].id if parent_slug else None,
            )
            session.add(category)
            session.flush()
            categories[slug] = category
            created_categories += 1
        for sequence, (name, slug, price, unit, stock, minimum) in enumerate(PRODUCTS, start=1):
            barcode = generate_internal_ean13(sequence)
            if barcode in existing_barcodes:
                continue
            product = Product(
                name=name,
                barcode=barcode,
                category_id=categories[slug].id,
                unit=ProductUnit(unit),
                price_minor=price * 100,
                stock_quantity=stock,
                min_stock_quantity=minimum,
                is_active=sequence != len(PRODUCTS),
            )
            session.add(product)
            session.flush()
            if stock:
                session.add(
                    StockMovement(product_id=product.id, delta=stock, reason=StockReason.RESTOCK)
                )
            created_products += 1
        return {"categories_created": created_categories, "products_created": created_products}

    return run_write(factory, operation)


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        result = seed_catalog(create_session_factory(engine))
        print(
            f"Создано категорий: {result['categories_created']}; "
            f"товаров: {result['products_created']}."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

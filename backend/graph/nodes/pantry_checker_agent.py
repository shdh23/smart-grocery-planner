from sqlalchemy.orm import Session
from sqlalchemy import func
from models.schemas import Ingredient, PantryCheckResult
from models.state import GroceryState
from db.connection import SessionLocal
from db.models import Pantry
from typing import Optional


# normalize to grams or ml so we can compare pantry vs list
UNIT_TO_BASE = {
    "g":    1,
    "kg":   1000,
    "oz":   28.35,
    "lb":   453.59,
    "ml":   1,
    "l":    1000,
    "cup":  240,
    "tbsp": 15,
    "tsp":  5,
    "pieces": 1,
    "piece":  1,
    "pinch":  1,
}

WEIGHT_UNITS  = {"g", "kg", "oz", "lb"}
VOLUME_UNITS  = {"ml", "l", "cup", "tbsp", "tsp"}
COUNT_UNITS   = {"pieces", "piece", "pinch"}


def to_base(quantity: float, unit: str) -> Optional[float]:
    """Quantity in base unit (g or ml). None if unit unknown."""
    unit = unit.lower().strip()
    factor = UNIT_TO_BASE.get(unit)
    if factor is None:
        return None
    return quantity * factor


def from_base(quantity_base: float, target_unit: str) -> float:
    """Convert base amount back to target unit."""
    target_unit = target_unit.lower().strip()
    factor = UNIT_TO_BASE.get(target_unit, 1)
    return round(quantity_base / factor, 2)


def units_compatible(unit_a: str, unit_b: str) -> bool:
    """Same kind of unit (both weight, both volume, or both count)."""
    a, b = unit_a.lower(), unit_b.lower()
    if a in WEIGHT_UNITS and b in WEIGHT_UNITS:
        return True
    if a in VOLUME_UNITS and b in VOLUME_UNITS:
        return True
    if a in COUNT_UNITS and b in COUNT_UNITS:
        return True
    return False


def load_pantry(user_id: str) -> dict[str, Pantry]:
    """All pantry items for user, keyed by lowercase ingredient name."""
    db: Session = SessionLocal()
    try:
        items = db.query(Pantry).filter(Pantry.user_id == user_id).all()
        return {item.ingredient_name.lower(): item for item in items}
    finally:
        db.close()


def find_pantry_match(
    ingredient_name: str,
    pantry: dict[str, Pantry]
) -> Optional[Pantry]:
    """Match ingredient to pantry by name (exact then substring)."""
    name = ingredient_name.lower().strip()

    if name in pantry:
        return pantry[name]

    for key, item in pantry.items():
        if key in name or name in key:
            return item

    return None


PANTRY_CATEGORIES = {
    "spice", "oil", "grain", "legume", "canned",
    "sauce", "condiment", "dry", "flour", "sugar",
    "dairy", "meat", "seafood", "produce", "frozen",
    "beverage", "snack", "bakery", "other"
}


def pantry_checker_agent(state: GroceryState) -> GroceryState:
    """Compare list to pantry: enough -> skip, partial -> reduce qty, restock when below threshold."""
    consolidated  = state.get("consolidated", [])
    user_id       = state["user_id"]

    print(f"PantryChecker: {len(consolidated)} ingredients vs pantry")

    try:
        pantry = load_pantry(user_id)
        print(f"  Pantry: {len(pantry)} items")

        updated_ingredients: list[Ingredient] = []
        pantry_sufficient:   list[str]        = []
        pantry_low:          list[dict]        = []
        pantry_deductions:   list[dict]        = []

        for ingredient in consolidated:

            if ingredient.category.lower() not in PANTRY_CATEGORIES:
                updated_ingredients.append(ingredient)
                continue

            pantry_item = find_pantry_match(ingredient.name, pantry)

            if not pantry_item:
                updated_ingredients.append(ingredient)
                continue

            if not units_compatible(ingredient.unit, pantry_item.unit):
                ingredient.notes = (
                    f"{ingredient.notes or ''} "
                    f"[Pantry has {pantry_item.quantity}{pantry_item.unit} "
                    f"but units are incompatible]"
                ).strip()
                updated_ingredients.append(ingredient)
                continue

            needed_base    = to_base(ingredient.quantity,       ingredient.unit)
            in_pantry_base = to_base(pantry_item.quantity,       pantry_item.unit)
            thr_unit       = getattr(pantry_item, "restock_threshold_unit", None) or pantry_item.unit
            threshold_base = to_base(pantry_item.restock_threshold, thr_unit)

            if needed_base is None or in_pantry_base is None:
                updated_ingredients.append(ingredient)
                continue

            will_remain_base = in_pantry_base - needed_base
            below_threshold  = threshold_base is not None and will_remain_base < threshold_base

            if in_pantry_base >= needed_base:
                remaining_display = from_base(will_remain_base, pantry_item.unit)

                pantry_deductions.append({
                    "ingredient_name": pantry_item.ingredient_name,
                    "deduct_amount":   ingredient.quantity,
                    "unit":            ingredient.unit,
                    "remaining":       remaining_display,
                    "remaining_unit":  pantry_item.unit
                })

                if below_threshold:
                    restock_amount = from_base(
                        threshold_base * 3 - will_remain_base,  # buy back up to 3x threshold
                        pantry_item.unit
                    )
                    restock_amount = max(round(restock_amount, 2), round(pantry_item.restock_threshold, 2))

                    pantry_low.append({
                        "name":            ingredient.name,
                        "have":            pantry_item.quantity,
                        "need":            ingredient.quantity,
                        "unit":            pantry_item.unit,
                        "will_remain":     remaining_display,
                        "threshold":       pantry_item.restock_threshold,
                        "preferred_store": pantry_item.preferred_store,
                        "status":          "low_after_use"
                    })

                    # Add "in pantry" marker so user knows they have it this week
                    pantry_sufficient.append(ingredient.name)

                    # Also add a restock item to the buy list
                    restock_ingredient = Ingredient(
                        name=ingredient.name,
                        quantity=restock_amount,
                        unit=pantry_item.unit,
                        category=ingredient.category,
                        notes=f"Restock — will have {remaining_display}{pantry_item.unit} left after this week"
                    )
                    updated_ingredients.append(restock_ingredient)

                else:
                    pantry_sufficient.append(ingredient.name)
                    info_ingredient = Ingredient(
                        name=ingredient.name,
                        quantity=0,
                        unit=ingredient.unit,
                        category=ingredient.category,
                        notes=f"In pantry — {pantry_item.quantity}{pantry_item.unit} available"
                    )
                    updated_ingredients.append(info_ingredient)

            else:
                to_buy_base    = needed_base - in_pantry_base
                to_buy_display = from_base(to_buy_base, ingredient.unit)

                note = (
                    f"Partial — have {pantry_item.quantity}{pantry_item.unit}, "
                    f"need {ingredient.quantity}{ingredient.unit}. "
                    f"Buy {to_buy_display}{ingredient.unit} more."
                )

                pantry_low.append({
                    "name":            ingredient.name,
                    "have":            pantry_item.quantity,
                    "need":            ingredient.quantity,
                    "to_buy":          to_buy_display,
                    "unit":            pantry_item.unit,
                    "will_remain":     0,
                    "threshold":       pantry_item.restock_threshold,
                    "preferred_store": pantry_item.preferred_store,
                    "status":          "partial"
                })

                pantry_deductions.append({
                    "ingredient_name": pantry_item.ingredient_name,
                    "deduct_amount":   pantry_item.quantity,
                    "unit":            pantry_item.unit,
                    "remaining":       0,
                    "remaining_unit":  pantry_item.unit
                })

                reduced_ingredient = Ingredient(
                    name=ingredient.name,
                    quantity=to_buy_display,
                    unit=ingredient.unit,
                    category=ingredient.category,
                    notes=note
                )
                updated_ingredients.append(reduced_ingredient)

        print(f"PantryChecker done: sufficient {len(pantry_sufficient)}, low/partial {len(pantry_low)}")
        if pantry_low:
            for item in pantry_low:
                if item["status"] == "low_after_use":
                    print(f"  - {item['name']}: will have {item['will_remain']}{item['unit']} left")
                else:
                    print(f"  - {item['name']}: buy {item.get('to_buy', item['need'])}{item['unit']} more")

        return {
            "consolidated":      updated_ingredients,
            "pantry_sufficient": pantry_sufficient,
            "pantry_low":        pantry_low,
            "pantry_deductions": pantry_deductions,
        }

    except Exception as e:
        print(f"PantryChecker failed: {e}")
        return {
            "pantry_sufficient": [],
            "pantry_low":        [],
            "pantry_deductions": [],
        }
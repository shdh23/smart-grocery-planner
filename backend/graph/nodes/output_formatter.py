from models.schemas import Ingredient
from models.state import GroceryState
from typing import Any


def merge_store_lists(
    routed_food:  dict[str, list[Ingredient]],
    routed_extra: dict[str, list[Ingredient]]
) -> dict[str, dict]:
    all_stores = set(routed_food.keys()) | set(routed_extra.keys())
    merged = {}
    for store in sorted(all_stores):
        merged[store] = {
            "food_items":  routed_food.get(store, []),
            "extra_items": routed_extra.get(store, [])
        }
    return merged


def format_store_summary(store: str, data: dict) -> str:
    food_count  = len(data["food_items"])
    extra_count = len(data["extra_items"])
    fsa_count   = sum(1 for i in data["extra_items"] if i.fsa_eligible)
    parts = []
    if food_count:
        parts.append(f"{food_count} food items")
    if extra_count:
        parts.append(f"{extra_count} extra items")
    if fsa_count:
        parts.append(f"{fsa_count} FSA eligible")
    return f"  {store.upper().replace('_', ' ')}: {', '.join(parts)}"


def serialize_ingredient(ing: Ingredient) -> dict:
    return {
        "name":         ing.name,
        "quantity":     ing.quantity,
        "unit":         ing.unit,
        "category":     ing.category,
        "store":        ing.store,
        "fsa_eligible": ing.fsa_eligible or False,
        "notes":        ing.notes or ""
    }


def output_formatter(state: GroceryState) -> GroceryState:
    """Merge routed food + extra into final_output (grocery_lists, pantry bits, stats)."""
    print("OutputFormatter: assembling final list...")

    routed_food        = state.get("routed_food",        {})
    routed_extra       = state.get("routed_extra",       {})
    fsa_flagged        = state.get("fsa_flagged",        [])
    needs_input        = state.get("needs_user_input",   [])
    pantry_sufficient  = state.get("pantry_sufficient",  [])
    pantry_low         = state.get("pantry_low",         [])
    pantry_deductions  = state.get("pantry_deductions",  [])

    if not routed_food and not routed_extra:
        print("OutputFormatter: no routed items")
        return {
            "final_output": {
                "grocery_lists":   [],
                "pantry_skipped":  pantry_sufficient,
                "pantry_restock":  pantry_low,
                "fsa_summary":     [],
                "needs_user_input":needs_input,
                "pantry_deductions": pantry_deductions,
                "stats": {"total_items": 0, "total_stores": 0, "fsa_count": 0}
            }
        }

    merged = merge_store_lists(routed_food, routed_extra)

    grocery_lists = []
    total_items   = 0
    for store, data in merged.items():
        food_count  = len(data["food_items"])
        extra_count = len(data["extra_items"])
        total_items += food_count + extra_count
        grocery_lists.append({
            "store":       store,
            "food_items":  [serialize_ingredient(i) for i in data["food_items"]],
            "extra_items": [serialize_ingredient(i) for i in data["extra_items"]],
            "count":       food_count + extra_count
        })

    fsa_summary = []
    for store, data in merged.items():
        for item in data["extra_items"]:
            if item.fsa_eligible:
                fsa_summary.append({
                    "name":  item.name,
                    "store": store,
                    "notes": item.notes or ""
                })

    stats = {
        "total_items":     total_items,
        "total_stores":    len(merged),
        "fsa_count":       len(fsa_summary),
        "food_count":      sum(len(v["food_items"])  for v in merged.values()),
        "extra_count":     sum(len(v["extra_items"]) for v in merged.values()),
        "pantry_skipped":  len(pantry_sufficient),
        "pantry_restock":  len(pantry_low),
    }

    print(f"\nFinal list: {stats['total_stores']} stores, {stats['total_items']} items\n")
    for store, data in merged.items():
        print(format_store_summary(store, data))

    if pantry_sufficient:
        print(f"\n  Skipped (in pantry): {len(pantry_sufficient)}")
        for name in pantry_sufficient:
            print(f"     - {name}")

    if pantry_low:
        print(f"\n  Restock soon: {len(pantry_low)}")
        for item in pantry_low:
            if item["status"] == "low_after_use":
                print(f"     - {item['name']}: {item['will_remain']}{item['unit']} left")
                if item.get("preferred_store"):
                    print(f"       buy from: {item['preferred_store']}")
            else:
                print(f"     - {item['name']}: buy {item.get('to_buy', item['need'])}{item['unit']} more")

    if fsa_summary:
        print(f"\n  FSA/HSA eligible: {len(fsa_summary)}")
        for item in fsa_summary:
            print(f"     - {item['name']} @ {item['store'].replace('_', ' ')}")

    if needs_input:
        print(f"\n  Needs input: {len(needs_input)}")
        for item in needs_input:
            print(f"     - {item['name']}: {item.get('unavailable_reason', '')}")
            if item.get("alternatives"):
                print(f"       alt: {item['alternatives']}")

    print("")

    final_output: dict[str, Any] = {
        "grocery_lists":     grocery_lists,
        "pantry_skipped":    pantry_sufficient,
        "pantry_restock":    pantry_low,
        "pantry_deductions": pantry_deductions,
        "fsa_summary":       fsa_summary,
        "needs_user_input":  needs_input,
        "stats":             stats
    }

    return {
        "final_output": final_output,
        "error":        None
    }
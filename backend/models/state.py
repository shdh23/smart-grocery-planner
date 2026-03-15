from typing import TypedDict, Optional
from models.schemas import Ingredient, PantryDeduction


class GroceryState(TypedDict):
    meals:                list[str]
    extra_items:          list[str]
    user_id:              str
    num_people:           int
    active_stores:        list[str]
    item_store_overrides: Optional[dict[str, str]] = None

    raw_ingredients:  list[Ingredient]
    consolidated:     list[Ingredient]
    pantry_sufficient: list[str]
    pantry_low:        list[dict]
    pantry_deductions: list[dict]
    routed_food:      dict[str, list[Ingredient]]

    extra_ingredients: list[Ingredient]
    fsa_flagged:       list[str]
    routed_extra:      dict[str, list[Ingredient]]

    needs_user_input: list[dict]
    final_output:     dict
    error:            Optional[str]
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from enum import Enum

DEFAULT_STORES = ["trader_joes", "costco", "indian_store", "target"]

class UserConfig(BaseModel):
    user_id:       str = "default_user"
    active_stores: list[str] = Field(default=DEFAULT_STORES, min_length=1)
    num_people:    int = Field(default=1, ge=1, le=20)

class UpdateUserConfigRequest(BaseModel):
    active_stores: Optional[list[str]] = None
    num_people:    Optional[int] = Field(default=None, ge=1, le=20)

    model_config = {
        "json_schema_extra": {
            "example": {
                "active_stores": ["trader_joes", "indian_store"],
                "num_people": 4
            }
        }
    }


class PlanStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"


class Ingredient(BaseModel):
    name:         str
    quantity:     float
    unit:         str
    category:     str
    store:        Optional[str] = None
    fsa_eligible: Optional[bool] = None
    notes:        Optional[str]  = None


class CreatePlanRequest(BaseModel):
    meals:                 list[str]
    extra_items:           list[str]          = []
    week_start_date:       Optional[date]      = None
    user_id:               str                = "default_user"
    num_people:            Optional[int]      = None
    active_stores:         Optional[list[str]]= None
    item_store_overrides:  Optional[dict[str, str]] = None
    meal_hints:            Optional[list[dict]]   = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "meals":           ["Butter Chicken", "Pasta Primavera"],
                "extra_items":     ["ibuprofen 200mg", "SPF 50 sunscreen"],
                "week_start_date": "2025-03-10",
                "user_id":         "default_user",
                "num_people":      4,
                "active_stores":   ["trader_joes", "costco", "indian_store", "target"]
            }
        }
    }


class StoreList(BaseModel):
    """One store's list of items."""
    store:  str
    items:  list[Ingredient]
    count:  int

class CreatePlanResponse(BaseModel):
    plan_id:       UUID
    status:        PlanStatus
    week_start_date: date
    meals:         list[str]
    grocery_lists: list[StoreList]
    fsa_items:     list[Ingredient]
    created_at:    datetime


# ─────────────────────────────────────────
# HISTORY RESPONSE — for GET /api/history
# ─────────────────────────────────────────

class PlanSummary(BaseModel):
    plan_id:         UUID
    week_start_date: date
    meals:           list[str]
    status:          PlanStatus
    store_count:     int   # how many stores in this plan
    total_items:     int
    created_at:      datetime

class HistoryResponse(BaseModel):
    plans: list[PlanSummary]
    total: int

# ─────────────────────────────────────────
# PANTRY
# ─────────────────────────────────────────

class PantryItem(BaseModel):
    id:                Optional[UUID] = None
    user_id:           str = "default_user"
    ingredient_name:   str
    quantity:          float
    unit:              str
    category:          str        # spice | oil | grain | legume | canned
    restock_threshold: float = 0
    preferred_store:   Optional[str] = None
    last_updated:      Optional[datetime] = None


class PantryCheckResult(BaseModel):
    """Result for one ingredient after checking against pantry."""
    ingredient_name: str
    needed:          float       # what the recipe requires
    unit:            str
    in_pantry:       float       # what user currently has (0 if not in pantry)
    to_buy:          float       # what still needs to be bought (0 if pantry sufficient)
    status:          str         # "sufficient" | "partial" | "not_in_pantry"
    will_remain:     float       # how much will be left after cooking
    below_threshold: bool        # will it drop below restock_threshold after use?


class PantryDeduction(BaseModel):
    """Tracks what to deduct from pantry after pipeline completes."""
    ingredient_name: str
    deduct_amount:   float
    unit:            str
    remaining:       float       # quantity after deduction


# ─────────────────────────────────────────
# PANTRY API REQUEST/RESPONSE
# ─────────────────────────────────────────

class AddPantryItemRequest(BaseModel):
    ingredient_name:        str
    quantity:               float
    unit:                   str
    category:               str
    restock_threshold:      float = 0
    restock_threshold_unit: str   = "g"   
    preferred_store:        Optional[str] = None
 
class UpdatePantryItemRequest(BaseModel):
    quantity:               Optional[float] = None
    unit:                   Optional[str]   = None
    restock_threshold:      Optional[float] = None
    restock_threshold_unit: Optional[str]   = None   
    preferred_store:        Optional[str]   = None


class BulkAddPantryRequest(BaseModel):
    items: list[AddPantryItemRequest] = Field(..., min_length=1)


# ── Parse intent ("Anything to add or change?") ──
class ParseIntentRequest(BaseModel):
    message:        str
    meals:          list[str] = []
    extra_items:    list[str] = Field(default_factory=list, alias="extra_items")
    active_stores:  list[str] = Field(default_factory=list, alias="active_stores")
    num_people:    int = 2

    model_config = {"populate_by_name": True}


class ParseIntentResponse(BaseModel):
    add_meals:             Optional[list[str]] = None
    remove_meals:          Optional[list[str]] = None
    add_extras:            Optional[list[str]] = None
    remove_extras:         Optional[list[str]] = None
    add_stores:            Optional[list[str]] = None  # store slugs, e.g. idly_express
    remove_stores:         Optional[list[str]] = None
    set_num_people:        Optional[int] = None
    item_store_overrides:  Optional[dict[str, str]] = None  # e.g. {"idly batter": "idly_express"}
    summary:               Optional[str] = None
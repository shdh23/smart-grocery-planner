"""Called from main when user removes an item from the list. Classifies reason, runs action (add to pantry, skip, change store, etc.), returns result."""

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session
from db.models import UserFeedback, Pantry, StorePreference, GroceryList
from datetime import datetime, timezone


CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a smart grocery assistant. A user has removed an ingredient from their grocery list and given a reason.

Your job is to classify the reason into exactly ONE of these actions and extract relevant data.

ACTIONS:
1. ADD_TO_PANTRY    — User already has this item at home
   Examples: "I already have it", "have it at home", "in my pantry", "got it"
   Data needed: estimated quantity to add (use the original quantity if unsure)

2. SKIP_FOR_MEAL    — User doesn't use this ingredient in this specific recipe
   Examples: "I don't use this", "not in my recipe", "I make it differently", "not needed for this dish"
   Data needed: nothing extra

3. SKIP_ALWAYS      — User never uses this ingredient at all
   Examples: "I never use this", "I don't cook with this", "allergic", "don't like it"
   Data needed: nothing extra

4. CHANGE_STORE     — User wants this from a different store
   Examples: "get from Costco", "wrong store", "I buy this at Indian store", mentions a store name
   Data needed: new store name (normalize to: trader_joes, costco, indian_store, target, whole_foods, walmart)

5. WRONG_QUANTITY   — User wants a different quantity
   Examples: "too much", "I need less", "only need half", "wrong amount", mentions a specific number
   Data needed: corrected quantity and unit

Respond ONLY with valid JSON, no explanation:
{{
  "action": "ADD_TO_PANTRY" | "SKIP_FOR_MEAL" | "SKIP_ALWAYS" | "CHANGE_STORE" | "WRONG_QUANTITY",
  "confidence": "high" | "medium" | "low",
  "data": {{
    "quantity": <number or null>,
    "unit": "<string or null>",
    "store": "<string or null>",
    "note": "<brief explanation of your reasoning>"
  }},
  "user_message": "<friendly confirmation message to show the user, e.g. 'Got it — added turmeric to your pantry'>"
}}"""
    ),
    (
        "human",
        """Ingredient: {ingredient_name}
Meal: {meal_name}
Original quantity: {quantity} {unit}
User's reason for removing: "{reason}"

Classify this and decide what action to take."""
    )
])


def run_feedback_agent(
    user_id:         str,
    ingredient_name: str,
    meal_name:       str | None,
    reason:          str,
    store:           str | None,
    quantity:        float,
    unit:            str,
    plan_id:         str,
    db:              Session
) -> dict:
    """Called from remove-item endpoint. Classifies reason, runs action, saves feedback. Returns action + user_message + success."""

    try:
        llm   = ChatOpenAI(model="gpt-4o", temperature=0,
                           api_key=os.getenv("OPENAI_API_KEY"))
        chain = CLASSIFY_PROMPT | llm
        raw   = chain.invoke({
            "ingredient_name": ingredient_name,
            "meal_name":       meal_name or "general",
            "quantity":        quantity,
            "unit":            unit,
            "reason":          reason,
        })

        text = raw.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        action = result["action"]
        data   = result.get("data", {})
        msg    = result.get("user_message", f"Got it — {ingredient_name} removed")

    except Exception as e:
        return {
            "success":      False,
            "action":       "ERROR",
            "user_message": f"Something went wrong classifying your reason: {str(e)}"
        }

    try:
        action_data = {}

        if action == "ADD_TO_PANTRY":
            qty_to_add = data.get("quantity") or quantity
            unit_to_use = data.get("unit") or unit

            existing = db.query(Pantry).filter(
                Pantry.user_id == user_id,
                Pantry.ingredient_name.ilike(ingredient_name)
            ).first()

            if existing:
                existing.quantity    += qty_to_add
                existing.last_updated = datetime.now(timezone.utc)
                action_data = {"updated": True, "new_quantity": existing.quantity, "unit": existing.unit}
            else:
                category = _infer_category(ingredient_name, unit_to_use)
                new_item = Pantry(
                    user_id=           user_id,
                    ingredient_name=   ingredient_name,
                    quantity=          qty_to_add,
                    unit=              unit_to_use,
                    category=          category,
                    restock_threshold= 0,
                    preferred_store=   store
                )
                db.add(new_item)
                action_data = {"created": True, "quantity": qty_to_add, "unit": unit_to_use}

        elif action == "SKIP_FOR_MEAL":
            action_data = {"meal_name": meal_name}

        elif action == "SKIP_ALWAYS":
            meal_name   = None   # null = global skip
            action_data = {"global": True}

        elif action == "CHANGE_STORE":
            new_store = data.get("store") or store
            if new_store:
                existing_pref = db.query(StorePreference).filter(
                    StorePreference.user_id == user_id,
                    StorePreference.ingredient_pattern.ilike(ingredient_name)
                ).first()
                if existing_pref:
                    existing_pref.preferred_store = new_store
                else:
                    db.add(StorePreference(
                        user_id=            user_id,
                        ingredient_pattern= ingredient_name.lower(),
                        preferred_store=    new_store
                    ))
                action_data = {"new_store": new_store}

        elif action == "WRONG_QUANTITY":
            new_qty  = data.get("quantity") or quantity
            new_unit = data.get("unit") or unit
            _update_item_quantity(plan_id, ingredient_name, new_qty, new_unit, db)
            action_data = {"new_quantity": new_qty, "unit": new_unit}

        # ── 3. Always save feedback record ──
        db.add(UserFeedback(
            user_id=         user_id,
            meal_name=       meal_name,
            ingredient_name= ingredient_name.lower(),
            reason=          reason,
            action_taken=    action,
            action_data=     action_data
        ))
        db.commit()

        if action != "WRONG_QUANTITY":
            _remove_item_from_list(plan_id, ingredient_name, db)

        return {
            "success":      True,
            "action":       action,
            "action_data":  action_data,
            "user_message": msg
        }

    except Exception as e:
        db.rollback()
        return {
            "success":      False,
            "action":       action,
            "user_message": f"Classified as {action} but execution failed: {str(e)}"
        }


def _infer_category(name: str, unit: str) -> str:
    name_lower = name.lower()
    if unit in ("g", "tsp", "tbsp") and any(w in name_lower for w in ["powder","masala","spice","salt","pepper","cumin","coriander","turmeric","chili"]):
        return "spice"
    if any(w in name_lower for w in ["oil","butter","ghee"]):
        return "oil"
    if any(w in name_lower for w in ["milk","cream","cheese","paneer","yogurt","curd"]):
        return "dairy"
    if any(w in name_lower for w in ["chicken","beef","lamb","fish","shrimp","meat"]):
        return "meat"
    if unit in ("ml", "l"):
        return "oil"
    return "produce"


def _remove_item_from_list(plan_id: str, ingredient_name: str, db: Session):
    """Remove an ingredient from all store rows in grocery_lists."""
    rows = db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id,
        GroceryList.store != "pantry_meta"
    ).all()

    for row in rows:
        items = dict(row.items)
        food_items  = items.get("food_items", [])
        extra_items = items.get("extra_items", [])

        new_food  = [i for i in food_items  if i["name"].lower() != ingredient_name.lower()]
        new_extra = [i for i in extra_items if i["name"].lower() != ingredient_name.lower()]

        if len(new_food) != len(food_items) or len(new_extra) != len(extra_items):
            items["food_items"]  = new_food
            items["extra_items"] = new_extra
            items["count"]       = len(new_food) + len(new_extra)
            row.items            = items

    db.commit()


def _update_item_quantity(plan_id: str, ingredient_name: str, new_qty: float, new_unit: str, db: Session):
    """Update quantity for an ingredient in grocery_lists."""
    rows = db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id,
        GroceryList.store != "pantry_meta"
    ).all()

    for row in rows:
        items      = dict(row.items)
        food_items = items.get("food_items", [])
        updated    = False
        for item in food_items:
            if item["name"].lower() == ingredient_name.lower():
                item["quantity"] = new_qty
                item["unit"]     = new_unit
                updated          = True
        if updated:
            items["food_items"] = food_items
            row.items           = items

    db.commit()
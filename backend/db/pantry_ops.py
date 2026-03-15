"""
Pantry DB ops. Deductions run only when user confirms the plan (POST /api/plan/{id}/confirm).
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from db.models import Pantry, MealPlan, GroceryList
from datetime import datetime, timezone
import json


def apply_pantry_deductions(
    plan_id: str,
    user_id: str,
    db: Session
) -> dict:
    """Load plan + grocery list, pull pantry_deductions from stored output, deduct from pantry, mark plan confirmed. Returns what we deducted and any restock alerts."""

    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.user_id == user_id
    ).first()

    if not plan:
        raise ValueError(f"Plan {plan_id} not found for user {user_id}")

    if plan.confirmed:
        raise ValueError(f"Plan {plan_id} has already been confirmed")

    # deductions live in the pantry_meta row that output_formatter wrote
    grocery_lists = db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id
    ).all()

    if not grocery_lists:
        raise ValueError(f"No grocery list found for plan {plan_id}")

    pantry_deductions = []
    for gl in grocery_lists:
        items = gl.items if isinstance(gl.items, dict) else {}
        if gl.store == "pantry_meta":
            pantry_deductions = items.get("pantry_deductions", [])
            break

    if not pantry_deductions:
        _mark_confirmed(plan, db)
        return {
            "confirmed":       True,
            "deductions_made": [],
            "restock_alerts":  [],
            "message":         "Plan confirmed. No pantry items were used this week."
        }

    deductions_made = []
    restock_alerts  = []

    for deduction in pantry_deductions:
        ingredient_name = deduction["ingredient_name"]
        deduct_amount   = deduction["deduct_amount"]
        remaining       = deduction["remaining"]

        pantry_item = db.query(Pantry).filter(
            Pantry.user_id == user_id,
            func.lower(Pantry.ingredient_name) == ingredient_name.lower()
        ).first()

        if not pantry_item:
            continue

        old_quantity          = pantry_item.quantity
        pantry_item.quantity  = max(0, remaining)
        pantry_item.last_updated = datetime.now(timezone.utc)

        deductions_made.append({
            "name":      ingredient_name,
            "was":       old_quantity,
            "deducted":  deduct_amount,
            "now":       pantry_item.quantity,
            "unit":      pantry_item.unit
        })

        if pantry_item.quantity <= pantry_item.restock_threshold:
            restock_alerts.append({
                "name":            ingredient_name,
                "quantity":        pantry_item.quantity,
                "unit":            pantry_item.unit,
                "threshold":       pantry_item.restock_threshold,
                "preferred_store": pantry_item.preferred_store,
                "message":         (
                    f"Only {pantry_item.quantity}{pantry_item.unit} left — "
                    f"restock from {pantry_item.preferred_store or 'your preferred store'}"
                )
            })

    _mark_confirmed(plan, db)
    db.commit()

    print(f"Pantry deductions applied for plan {plan_id}")
    for d in deductions_made:
        print(f"  {d['name']}: {d['was']}{d['unit']} -> {d['now']}{d['unit']}")
    if restock_alerts:
        print(f"Restock alerts ({len(restock_alerts)}):")
        for alert in restock_alerts:
            print(f"  - {alert['message']}")

    return {
        "confirmed":       True,
        "deductions_made": deductions_made,
        "restock_alerts":  restock_alerts,
        "message":         (
            f"Plan confirmed! Deducted {len(deductions_made)} pantry items. "
            + (f"{len(restock_alerts)} items need restocking." if restock_alerts else "")
        )
    }


def _mark_confirmed(plan: MealPlan, db: Session):
    plan.confirmed    = True
    plan.confirmed_at = datetime.now(timezone.utc)
    plan.status       = "confirmed"
"""
main.py — Smart Grocery Planner FastAPI Backend

Endpoints:
  POST   /api/plan                  → run full pipeline
  GET    /api/plan/{id}             → fetch saved plan
  POST   /api/plan/{id}/confirm     → apply pantry deductions
  GET    /api/history               → past weekly plans
  GET    /api/stream/{id}           → SSE real-time agent progress

  GET    /api/pantry                → view pantry
  POST   /api/pantry                → add item
  POST   /api/pantry/bulk           → bulk add (first-time setup)
  PUT    /api/pantry/{id}           → update item
  DELETE /api/pantry/{id}           → remove item

  GET    /api/config                → get user config
  PUT    /api/config                → update stores / num_people
  GET    /api/preferences           → store routing preferences
  PUT    /api/preferences           → update ingredient → store rules
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.connection import engine, get_db, verify_connection
from db.models import Base, MealPlan, GroceryList, StorePreference, UserConfig, Pantry, Recipe, UserFeedback
from graph.nodes.feedback_agent import run_feedback_agent
from db.pantry_ops import apply_pantry_deductions
from models.schemas import (
    CreatePlanRequest, AddPantryItemRequest, UpdatePantryItemRequest,
    BulkAddPantryRequest, UserConfig as UserConfigSchema,
    DEFAULT_STORES
)
from models.state import GroceryState
from graph.graph import grocery_graph
from auth import get_current_user


# in-memory: plan_id -> list of progress events (filled by background pipeline)
progress_store: dict[str, list[dict]] = {}
plan_complete:  dict[str, bool]       = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Smart Grocery Planner API...")
    Base.metadata.create_all(bind=engine)
    verify_connection()
    yield
    print("Shutting down...")


app = FastAPI(
    title="Smart Grocery Planner",
    description="AI-powered weekly grocery planner with pantry tracking and FSA/HSA checking",
    version="1.0.0",
    lifespan=lifespan
)

import os as _os  # allowed origins from env
_raw_origins = _os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
_allowed_origins = [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_or_create_user_config(user_id: str, db: Session) -> UserConfig:
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        config = UserConfig(
            user_id=user_id,
            active_stores=DEFAULT_STORES,
            num_people=1
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def push_progress(plan_id: str, event: str, data: dict):
    """Append one progress event to the SSE store for this plan."""
    if plan_id not in progress_store:
        progress_store[plan_id] = []
    progress_store[plan_id].append({
        "event": event,
        "data":  data,
        "ts":    datetime.now(timezone.utc).isoformat()
    })


def save_grocery_list(plan_id: str, final_output: dict, db: Session):
    """Persist final grocery list to DB. Clears existing rows for this plan first so we don't get duplicate keys if formatter runs again."""
    # clear any partial rows from a previous run
    db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id
    ).delete(synchronize_session=False)
    db.commit()

    # insert one row per store
    grocery_lists = final_output.get("grocery_lists", [])
    for store_data in grocery_lists:
        db.add(GroceryList(
            meal_plan_id=plan_id,
            store=store_data["store"],
            items={
                "food_items":  store_data["food_items"],
                "extra_items": store_data["extra_items"],
                "count":       store_data["count"]
            }
        ))

    # one extra row for pantry metadata (deductions, restock, etc.)
    deductions = final_output.get("pantry_deductions", [])
    db.add(GroceryList(
        meal_plan_id=plan_id,
        store="pantry_meta",
        items={
            "pantry_deductions": deductions,
            "pantry_skipped":    final_output.get("pantry_skipped", []),
            "pantry_restock":    final_output.get("pantry_restock", []),
        }
    ))

    db.commit()


def run_pipeline_task(plan_id: str, state: GroceryState, db_url: str):
    """Runs the pipeline in a background thread and pushes SSE as each node finishes. Uses its own DB session."""
    from db.connection import SessionLocal

    push_progress(plan_id, "pipeline_start", {
        "message": "Pipeline started",
        "meals":   state["meals"],
        "people":  state["num_people"]
    })

    try:
        db = SessionLocal()

        # messages we send to the client as each node finishes (merge_barrier is internal, no message)
        NODE_MESSAGES = {
            "recipe_agent":             "Extracting ingredients",
            "extra_items_agent":        "Structuring extra items",
            "consolidation_agent":      "Consolidating ingredient list",
            "pantry_checker_agent":     "Checking your pantry",
            "fsa_checker_agent":        "Checking FSA/HSA eligibility",
            "store_router_agent_food":  "Routing food items to stores",
            "store_router_agent_extra": "Routing extra items to stores",
            "merge_barrier":            None,
            "output_formatter":         "Assembling final grocery list",
        }

        for chunk in grocery_graph.stream(state, stream_mode="updates"):
            for node_name, node_data in chunk.items():
                msg = NODE_MESSAGES.get(node_name)
                if msg:
                    push_progress(plan_id, "node_complete", {
                        "node":    node_name,
                        "message": msg,
                    })

        final_state  = grocery_graph.invoke(state)
        final_output = final_state.get("final_output", {})
        stats        = final_output.get("stats", {})

        plan = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
        if plan:
            plan.status = "complete"
            db.commit()

        save_grocery_list(plan_id, final_output, db)

        push_progress(plan_id, "pipeline_complete", {
            "message":        "✅ Grocery list is ready!",
            "stats":          stats,
            "pantry_skipped": final_output.get("pantry_skipped", []),
            "pantry_restock": final_output.get("pantry_restock", []),
        })

        db.close()

    except Exception as e:
        push_progress(plan_id, "pipeline_error", {
            "message": f"Pipeline failed: {str(e)}"
        })
        try:
            db = SessionLocal()
            plan = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
            if plan:
                plan.status = "failed"
                db.commit()
            db.close()
        except:
            pass

    finally:
        plan_complete[plan_id] = True


@app.post("/api/plan", status_code=202)
def create_plan(
    request:    CreatePlanRequest,
    background: BackgroundTasks,
    db:         Session = Depends(get_db),
    user_id:    str     = Depends(get_current_user)
):
    """Start the pipeline in the background. Returns plan_id right away; client can poll /api/stream/{id} for progress."""
    config = get_or_create_user_config(user_id, db)
    active_stores = request.active_stores or config.active_stores
    num_people    = request.num_people    or config.num_people

    plan = MealPlan(
        user_id=         user_id,
        week_start_date= request.week_start_date or date.today(),
        meals=           request.meals,
        num_people=      num_people,
        active_stores=   active_stores,
        status=          "running"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    plan_id = str(plan.id)

    state: GroceryState = {
        "meals":             request.meals,
        "extra_items":       request.extra_items or [],
        "user_id":           user_id,
        "num_people":        num_people,
        "active_stores":     active_stores,
        "raw_ingredients":   [],
        "consolidated":      [],
        "routed_food":       {},
        "extra_ingredients": [],
        "fsa_flagged":       [],
        "routed_extra":      {},
        "pantry_sufficient": [],
        "pantry_low":        [],
        "pantry_deductions": [],
        "needs_user_input":  [],
        "meal_hints":        request.meal_hints or [],
        "final_output":      {},
        "error":             None
    }

    progress_store[plan_id] = []
    plan_complete[plan_id]  = False

    from db.connection import DATABASE_URL
    background.add_task(run_pipeline_task, plan_id, state, DATABASE_URL)

    return {
        "plan_id":    plan_id,
        "status":     "running",
        "message":    "Pipeline started. Connect to /api/stream/{plan_id} for live progress.",
        "stream_url": f"/api/stream/{plan_id}"
    }


@app.get("/api/plan/{plan_id}")
def get_plan(
    plan_id: str,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Fetch a completed grocery list by plan ID."""
    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.user_id == user_id
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    grocery_lists = db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id,
        GroceryList.store != "pantry_meta"
    ).all()

    meta = db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id,
        GroceryList.store == "pantry_meta"
    ).first()

    return {
        "plan_id":        plan_id,
        "status":         plan.status,
        "confirmed":      plan.confirmed,
        "confirmed_at":   plan.confirmed_at,
        "meals":          plan.meals,
        "num_people":     plan.num_people,
        "active_stores":  plan.active_stores,
        "week_start_date":str(plan.week_start_date),
        "created_at":     plan.created_at.isoformat(),
        "grocery_lists":  [
            {
                "store":       gl.store,
                "food_items":  gl.items.get("food_items", []),
                "extra_items": gl.items.get("extra_items", []),
                "count":       gl.items.get("count", 0)
            }
            for gl in grocery_lists
        ],
        "pantry_skipped":    meta.items.get("pantry_skipped", [])    if meta else [],
        "pantry_restock":    meta.items.get("pantry_restock", [])    if meta else [],
        "pantry_deductions": meta.items.get("pantry_deductions", []) if meta else [],
    }


@app.post("/api/plan/{plan_id}/confirm")
def confirm_plan(
    plan_id: str,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """
    User says 'looks good' — apply pantry deductions and mark plan confirmed.
    """
    try:
        result = apply_pantry_deductions(plan_id, user_id, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/history")
def get_history(
    limit:   int = 10,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Return past weekly plans, most recent first."""
    plans = (
        db.query(MealPlan)
        .filter(MealPlan.user_id == user_id)
        .order_by(MealPlan.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "plan_id":        str(p.id),
            "week_start_date":str(p.week_start_date),
            "meals":          p.meals,
            "num_people":     p.num_people,
            "status":         p.status,
            "confirmed":      p.confirmed,
            "created_at":     p.created_at.isoformat()
        }
        for p in plans
    ]


async def event_generator(plan_id: str) -> AsyncGenerator[str, None]:
    """SSE: poll progress_store every 500ms and yield new events until pipeline is done."""
    sent_index = 0

    while True:
        events = progress_store.get(plan_id, [])

        while sent_index < len(events):
            event = events[sent_index]
            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'])}\n\n"
            sent_index += 1

        if plan_complete.get(plan_id) and sent_index >= len(events):
            yield "event: done\ndata: {}\n\n"
            break

        await asyncio.sleep(0.5)


@app.get("/api/stream/{plan_id}")
async def stream_plan(plan_id: str):
    """SSE stream for a running plan. Events: pipeline_start, node_complete, pipeline_complete, pipeline_error, done."""
    if plan_id not in progress_store:
        raise HTTPException(status_code=404, detail="Plan not found or not started yet")

    return StreamingResponse(
        event_generator(plan_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",    # disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        }
    )



def normalize_pantry_units(ingredient_name: str, quantity: float, unit: str,
                            restock_threshold: float, category: str) -> dict:
    """Fix obvious unit mistakes: e.g. spices in kg -> g, oils in L -> ml; cap threshold so it's not above quantity."""
    q, u, t = quantity, unit.lower(), restock_threshold

    if category in ("spice",) and u == "kg" and q > 1:
        q = q * 1000
        t = t * 1000 if t > 0 else t
        u = "g"

    if category in ("oil",) and u == "l" and q > 20:
        q = q * 1000
        t = t * 1000 if t > 0 else t
        u = "ml"

    # If threshold > quantity, it's clearly wrong — disable it
    if t > 0 and t >= q:
        t = 0

    return {"quantity": round(q, 2), "unit": u, "restock_threshold": round(t, 2)}

@app.get("/api/pantry")
def get_pantry(
    category: Optional[str] = None,
    db:       Session = Depends(get_db),
    user_id:  str           = Depends(get_current_user)
):
    """Get all pantry items, optionally filtered by category."""
    query = db.query(Pantry).filter(Pantry.user_id == user_id)
    if category:
        query = query.filter(Pantry.category == category)
    items = query.order_by(Pantry.category, Pantry.ingredient_name).all()

    def needs_restock(item) -> bool:
        """
        Unit-aware restock check.
        quantity and restock_threshold can have DIFFERENT units.
        Both are converted to base units (g or ml) before comparing.
        """
        if item.restock_threshold <= 0:
            return False
        unit_to_base = {
            "g": 1, "kg": 1000, "mg": 0.001,
            "ml": 1, "l": 1000,
            "tsp": 5, "tbsp": 15, "cup": 240, "cups": 240,
            "pieces": 1, "piece": 1
        }
        qty_unit = (item.unit or "g").lower().strip()
        thr_unit = (item.restock_threshold_unit or item.unit or "g").lower().strip()
        qty_base = item.quantity          * unit_to_base.get(qty_unit, 1)
        thr_base = item.restock_threshold * unit_to_base.get(thr_unit, 1)
        return qty_base <= thr_base

    return [
        {
            "id":                str(item.id),
            "ingredient_name":   item.ingredient_name,
            "quantity":          item.quantity,
            "unit":              item.unit,
            "category":          item.category,
            "restock_threshold": item.restock_threshold,
            "preferred_store":   item.preferred_store,
            "last_updated":      item.last_updated.isoformat() if item.last_updated else None,
            "needs_restock":     needs_restock(item),
            "quantity_display":  f"{item.quantity} {item.unit}",
            "threshold_display": f"{item.restock_threshold} {item.restock_threshold_unit or item.unit}" if item.restock_threshold > 0 else None,
            "restock_threshold_unit": item.restock_threshold_unit or item.unit,
        }
        for item in items
    ]


@app.post("/api/pantry", status_code=201)
def add_pantry_item(
    request: AddPantryItemRequest,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Add a single item to the pantry."""
    existing = db.query(Pantry).filter(
        Pantry.user_id == user_id,
        Pantry.ingredient_name == request.ingredient_name
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"'{request.ingredient_name}' already in pantry. Use PUT to update."
        )

    normalized = normalize_pantry_units(
        request.ingredient_name, request.quantity, request.unit,
        request.restock_threshold, request.category
    )

    item = Pantry(
        user_id=           user_id,
        ingredient_name=   request.ingredient_name,
        quantity=          normalized["quantity"],
        unit=              normalized["unit"],
        category=          request.category,
        restock_threshold= normalized["restock_threshold"],
        preferred_store=   request.preferred_store
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {"id": str(item.id), "message": f"Added '{request.ingredient_name}' to pantry"}


@app.post("/api/pantry/bulk", status_code=201)
def bulk_add_pantry(
    request:   BulkAddPantryRequest,
    overwrite: bool    = False,
    db:        Session = Depends(get_db),
    user_id:   str     = Depends(get_current_user)
):
    """
    Add multiple pantry items at once.
    overwrite=true → update quantity/threshold for existing items.
    overwrite=false → skip duplicates.
    """
    added     = []
    updated   = []
    skipped   = []

    for item_req in request.items:
        existing = db.query(Pantry).filter(
            Pantry.user_id == user_id,
            Pantry.ingredient_name.ilike(item_req.ingredient_name)
        ).first()

        if existing:
            if overwrite:
                norm = normalize_pantry_units(
                    item_req.ingredient_name, item_req.quantity, item_req.unit,
                    item_req.restock_threshold, item_req.category
                )
                existing.quantity          = norm["quantity"]
                existing.unit              = norm["unit"]
                existing.category          = item_req.category
                existing.restock_threshold = norm["restock_threshold"]
                if item_req.preferred_store:
                    existing.preferred_store = item_req.preferred_store
                updated.append(item_req.ingredient_name)
            else:
                skipped.append(item_req.ingredient_name)
            continue

        norm = normalize_pantry_units(
            item_req.ingredient_name, item_req.quantity, item_req.unit,
            item_req.restock_threshold, item_req.category
        )
        item = Pantry(
            user_id=           user_id,
            ingredient_name=   item_req.ingredient_name,
            quantity=          norm["quantity"],
            unit=              norm["unit"],
            category=          item_req.category,
            restock_threshold= norm["restock_threshold"],
            preferred_store=   item_req.preferred_store
        )
        db.add(item)
        added.append(item_req.ingredient_name)

    db.commit()

    return {
        "added":   added,
        "updated": updated,
        "skipped": skipped,
        "message": f"Added {len(added)}, updated {len(updated)}, skipped {len(skipped)}."
    }


@app.put("/api/pantry/{item_id}")
def update_pantry_item(
    item_id: str,
    request: UpdatePantryItemRequest,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Update quantity, restock threshold, or preferred store for a pantry item."""
    item = db.query(Pantry).filter(
        Pantry.id == item_id,
        Pantry.user_id == user_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found")

    if request.quantity               is not None: item.quantity               = request.quantity
    if request.unit                   is not None: item.unit                   = request.unit
    if request.restock_threshold      is not None: item.restock_threshold      = request.restock_threshold
    if request.restock_threshold_unit is not None: item.restock_threshold_unit = request.restock_threshold_unit
    if request.preferred_store        is not None: item.preferred_store        = request.preferred_store

    item.last_updated = datetime.now(timezone.utc)
    db.commit()

    return {
        "id":                str(item.id),
        "ingredient_name":   item.ingredient_name,
        "quantity":          item.quantity,
        "unit":              item.unit,
        "restock_threshold": item.restock_threshold,
        "preferred_store":   item.preferred_store,
        "message":           "Updated"
    }


@app.delete("/api/pantry/{item_id}", status_code=204)
def delete_pantry_item(
    item_id: str,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Remove an item from the pantry."""
    item = db.query(Pantry).filter(
        Pantry.id == item_id,
        Pantry.user_id == user_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found")

    db.delete(item)
    db.commit()


@app.get("/api/config")
def get_config(
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Get user config: active stores + num_people."""
    config = get_or_create_user_config(user_id, db)
    return {
        "user_id":       config.user_id,
        "active_stores": config.active_stores,
        "num_people":    config.num_people,
        "updated_at":    config.updated_at.isoformat() if config.updated_at else None
    }


@app.put("/api/config")
def update_config(
    request: UserConfigSchema,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Update active stores and/or num_people."""
    config = get_or_create_user_config(user_id, db)

    if request.active_stores is not None: config.active_stores = request.active_stores
    if request.num_people    is not None: config.num_people    = request.num_people
    config.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "user_id":       user_id,
        "active_stores": config.active_stores,
        "num_people":    config.num_people,
        "message":       "Config updated"
    }


@app.get("/api/preferences")
def get_preferences(
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Get ingredient → store routing preferences."""
    prefs = db.query(StorePreference).filter(
        StorePreference.user_id == user_id
    ).order_by(StorePreference.ingredient_pattern).all()

    return [
        {
            "id":                str(p.id),
            "ingredient_pattern":p.ingredient_pattern,
            "preferred_store":   p.preferred_store
        }
        for p in prefs
    ]


@app.put("/api/preferences")
def upsert_preference(
    ingredient_pattern: str,
    preferred_store:    str,
    db:                 Session = Depends(get_db),
    user_id:            str     = Depends(get_current_user)
):
    """Set or update one ingredient -> store routing preference."""
    pref = db.query(StorePreference).filter(
        StorePreference.user_id == user_id,
        StorePreference.ingredient_pattern == ingredient_pattern
    ).first()

    if pref:
        pref.preferred_store = preferred_store
    else:
        pref = StorePreference(
            user_id=            user_id,
            ingredient_pattern= ingredient_pattern,
            preferred_store=    preferred_store
        )
        db.add(pref)

    db.commit()

    return {
        "ingredient_pattern": ingredient_pattern,
        "preferred_store":    preferred_store,
        "message":            "Preference saved"
    }




@app.post("/api/pantry/fix-units")
def fix_pantry_units(
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """One-off: normalize bad units on all pantry items. Safe to run again."""
    items = db.query(Pantry).filter(Pantry.user_id == user_id).all()
    fixed = []

    for item in items:
        norm = normalize_pantry_units(
            item.ingredient_name, item.quantity, item.unit,
            item.restock_threshold, item.category
        )
        if norm["quantity"] != item.quantity or norm["unit"] != item.unit or norm["restock_threshold"] != item.restock_threshold:
            item.quantity          = norm["quantity"]
            item.unit              = norm["unit"]
            item.restock_threshold = norm["restock_threshold"]
            fixed.append(item.ingredient_name)

    db.commit()
    return {
        "fixed": fixed,
        "message": f"Fixed {len(fixed)} items with incorrect units"
    }

@app.get("/api/recipes")
def get_recipes(
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Get all saved recipes for the current user."""
    recipes = db.query(Recipe).filter(
        Recipe.user_id == user_id
    ).order_by(Recipe.name).all()

    return [
        {
            "id":          str(r.id),
            "name":        r.name,
            "servings":    r.servings,
            "ingredients": r.ingredients,
            "created_at":  r.created_at.isoformat(),
            "updated_at":  r.updated_at.isoformat(),
        }
        for r in recipes
    ]


@app.post("/api/recipes", status_code=201)
def create_recipe(
    request: dict,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Save a new recipe. Body: name, servings, ingredients (list of {name, quantity, unit, category})."""
    name = request.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Recipe name is required")

    existing = db.query(Recipe).filter(
        Recipe.user_id == user_id,
        Recipe.name.ilike(name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Recipe '{name}' already exists. Use PUT to update.")

    recipe = Recipe(
        user_id=     user_id,
        name=        name,
        servings=    request.get("servings", 2),
        ingredients= request.get("ingredients", [])
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)

    return {
        "id":          str(recipe.id),
        "name":        recipe.name,
        "servings":    recipe.servings,
        "ingredients": recipe.ingredients,
        "message":     f"Recipe '{name}' saved"
    }


@app.put("/api/recipes/{recipe_id}")
def update_recipe(
    recipe_id: str,
    request:   dict,
    db:        Session = Depends(get_db),
    user_id:   str     = Depends(get_current_user)
):
    """Update an existing recipe."""
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.user_id == user_id
    ).first()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if "name"        in request: recipe.name        = request["name"]
    if "servings"    in request: recipe.servings    = request["servings"]
    if "ingredients" in request: recipe.ingredients = request["ingredients"]

    db.commit()
    return {"id": str(recipe.id), "name": recipe.name, "message": "Updated"}


@app.delete("/api/recipes/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: str,
    db:        Session = Depends(get_db),
    user_id:   str     = Depends(get_current_user)
):
    """Delete a saved recipe."""
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.user_id == user_id
    ).first()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    db.delete(recipe)
    db.commit()



@app.post("/api/plan/{plan_id}/remove-item")
def remove_item(
    plan_id:  str,
    request:  dict,
    db:       Session = Depends(get_db),
    user_id:  str     = Depends(get_current_user)
):
    """Remove item from list and record feedback. Body: ingredient_name, meal_name, reason, store, quantity, unit."""
    ingredient_name = request.get("ingredient_name", "").strip()
    reason          = request.get("reason", "").strip()

    if not ingredient_name:
        raise HTTPException(status_code=400, detail="ingredient_name is required")
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.user_id == user_id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    result = run_feedback_agent(
        user_id=         user_id,
        ingredient_name= ingredient_name,
        meal_name=       request.get("meal_name"),
        reason=          reason,
        store=           request.get("store"),
        quantity=        float(request.get("quantity", 0)),
        unit=            request.get("unit", "g"),
        plan_id=         plan_id,
        db=              db
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["user_message"])

    return result


@app.get("/api/feedback")
def get_feedback(
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """List recent feedback records (for debugging)."""
    records = db.query(UserFeedback).filter(
        UserFeedback.user_id == user_id
    ).order_by(UserFeedback.created_at.desc()).limit(100).all()

    return [
        {
            "id":              str(r.id),
            "meal_name":       r.meal_name,
            "ingredient_name": r.ingredient_name,
            "reason":          r.reason,
            "action_taken":    r.action_taken,
            "action_data":     r.action_data,
            "created_at":      r.created_at.isoformat()
        }
        for r in records
    ]



@app.post("/api/parse-intent")
def parse_intent(
    request: dict,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """Parse free-text instruction into add/remove meals, extras, stores, num_people, item_store_overrides. Accepts message or text + optional context."""
    import json

    text = (request.get("text") or request.get("message") or "").strip()
    current_state = request.get("current_state") or {
        "meals":          request.get("meals", []),
        "extra_items":    request.get("extra_items", []),
        "active_stores":  request.get("active_stores", []),
        "num_people":     request.get("num_people", 2),
    }

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    config       = get_or_create_user_config(user_id, db)
    known_stores = config.active_stores or []

    system_msg = f"""You are a grocery planning assistant. The user has typed a natural language instruction to modify their grocery plan.

Current plan state:
- Meals: {json.dumps(current_state.get("meals", []))}
- Extra items: {json.dumps(current_state.get("extra_items", []))}
- Active stores: {json.dumps(current_state.get("active_stores", []))}
- Number of people: {current_state.get("num_people", 2)}

User's known stores: {json.dumps(known_stores)}

Parse the instruction and return ONLY a valid JSON object with these optional keys:
  add_meals: list of clean meal names to add (no hints, just the name)
  remove_meals: list of meal names to remove
  add_extras: list of extra items to add
  remove_extras: list of extra items to remove
  add_stores: list of store IDs to add (snake_case)
  remove_stores: list of store IDs to remove
  set_num_people: integer or omit
  meal_hints: list of objects, one per meal that has buying instructions:
    meal: clean meal name
    ingredients: list of items to actually buy
    store: snake_case store ID where to buy them
    suggest_save_recipe: true
  summary: short human-readable summary of changes

MEAL HINT RULES:
- "Idli - I get batter from Idli Express" → add_meals: ["Idli"], meal_hints: [meal: "Idli", ingredients: ["idli batter"], store: "idli_express"]
- "Pasta (use store-bought sauce from Trader Joes)" → hint with ingredients: ["pasta sauce"], store: "trader_joes"
- Always add new store to add_stores as well

STORE ID RULES:
- Normalize to snake_case: "Idli Express" → "idli_express", "Whole Foods" → "whole_foods"
- If store exists in known_stores use exact ID

Return ONLY valid JSON, no markdown, no explanation."""

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        llm  = ChatOpenAI(model="gpt-4o", temperature=0, api_key=_os.getenv("OPENAI_API_KEY"))
        raw  = llm.invoke([SystemMessage(content=system_msg), HumanMessage(content=text)])

        result_text = raw.content.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        result = json.loads(result_text.strip())
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intent parsing failed: {str(e)}")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        db_ok = True
    except:
        db_ok = False
    return {
        "status":   "ok" if db_ok else "degraded",
        "db":       "connected" if db_ok else "disconnected",
        "version":  "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
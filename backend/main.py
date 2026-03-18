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
import os
import traceback
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


# ─────────────────────────────────────────
# SSE PROGRESS STORE
# In-memory dict: plan_id → list of progress events
# Populated by background task as pipeline runs
# ─────────────────────────────────────────
progress_store: dict[str, list[dict]] = {}
plan_complete:  dict[str, bool]       = {}



from fastapi import Request
from fastapi.responses import Response

# ─────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Smart Grocery Planner API...")
    Base.metadata.create_all(bind=engine)
    verify_connection()   # prints its own status message
    yield
    print("👋 Shutting down...")


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

app = FastAPI(
    title="Smart Grocery Planner",
    description="AI-powered weekly grocery planner with pantry tracking and FSA/HSA checking",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Content-Type"],
    expose_headers=["*"],
)


@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str, request: Request):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
        }
    )


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

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
    """Push a progress event to the SSE store for this plan."""
    if plan_id not in progress_store:
        progress_store[plan_id] = []
    progress_store[plan_id].append({
        "event": event,
        "data":  data,
        "ts":    datetime.now(timezone.utc).isoformat()
    })


def save_grocery_list(plan_id: str, final_output: dict, db: Session):
    """
    Save the final grocery list to DB.
    Deletes all existing rows for this plan first to avoid unique constraint
    violations if output_formatter fires more than once.
    """
    # ── Wipe any partial rows from a previous call ──
    db.query(GroceryList).filter(
        GroceryList.meal_plan_id == plan_id
    ).delete(synchronize_session=False)
    db.commit()

    # ── Insert fresh ──
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

    # ── Pantry meta row ──
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


# ─────────────────────────────────────────
# BACKGROUND TASK — run pipeline
# Runs in a thread pool so it doesn't block
# the event loop. Pushes SSE events as each
# node completes.
# ─────────────────────────────────────────

def run_pipeline_task(plan_id: str, state: GroceryState, db_url: str):
    """
    Background task: invoke the LangGraph pipeline and stream progress.
    Uses a fresh DB session (background threads can't share sessions).
    """
    from db.connection import SessionLocal

    push_progress(plan_id, "pipeline_start", {
        "message": "Pipeline started",
        "meals":   state["meals"],
        "people":  state["num_people"]
    })

    try:
        db = SessionLocal()

        # ── Push intermediate progress events ──
        NODE_MESSAGES = {
            "recipe_agent":             "🍽️  Extracting ingredients",
            "extra_items_agent":        "🛍️  Structuring extra items",
            "consolidation_agent":      "🔄 Consolidating ingredient list",
            "pantry_checker_agent":     "🥫 Checking your pantry",
            "fsa_checker_agent":        "💊 Checking FSA/HSA eligibility",
            "store_router_agent_food":  "🏪 Routing food items to stores",
            "store_router_agent_extra": "🏪 Routing extra items to stores",
            "merge_barrier":            None,   # skip — internal node
            "output_formatter":         "📋 Assembling final grocery list",
        }

        # Stream for SSE progress updates
        for chunk in grocery_graph.stream(state, stream_mode="updates"):
            for node_name, node_data in chunk.items():
                msg = NODE_MESSAGES.get(node_name)
                if msg:  # skip internal nodes like merge_barrier
                    push_progress(plan_id, "node_complete", {
                        "node":    node_name,
                        "message": msg,
                    })

        # ── Now invoke to get the complete final state ──
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
        # Mark plan as failed
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


# ─────────────────────────────────────────
# ── PLAN ENDPOINTS ──
# ─────────────────────────────────────────

@app.post("/api/plan", status_code=202)
def create_plan(
    request:    CreatePlanRequest,
    background: BackgroundTasks,
    db:         Session = Depends(get_db),
    user_id:    str     = Depends(get_current_user)
):
    """
    Submit meals + extra items → kick off pipeline in background.
    Returns plan_id immediately. Use GET /api/stream/{id} for progress.
    """
    # ── Load user config defaults if not provided ──
    config = get_or_create_user_config(user_id, db)
    active_stores = request.active_stores or config.active_stores
    num_people    = request.num_people    or config.num_people

    # ── Create meal plan row ──
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

    # ── Build initial state ──
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

    # ── Initialize SSE store for this plan ──
    progress_store[plan_id] = []
    plan_complete[plan_id]  = False

    # ── Run pipeline in background ──
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


# ─────────────────────────────────────────
# ── SSE STREAMING ──
# ─────────────────────────────────────────

async def event_generator(plan_id: str) -> AsyncGenerator[str, None]:
    """
    Yields SSE-formatted events as pipeline nodes complete.
    Polls progress_store every 500ms until pipeline_complete.
    """
    sent_index = 0

    while True:
        events = progress_store.get(plan_id, [])

        # Send any new events since last poll
        while sent_index < len(events):
            event = events[sent_index]
            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'])}\n\n"
            sent_index += 1

        # Stop streaming once pipeline is done
        if plan_complete.get(plan_id) and sent_index >= len(events):
            yield "event: done\ndata: {}\n\n"
            break

        await asyncio.sleep(0.5)


@app.get("/api/stream/{plan_id}")
async def stream_plan(plan_id: str):
    """
    SSE endpoint — stream real-time agent progress for a running plan.

    Frontend usage:
        const es = new EventSource(`/api/stream/${planId}`);
        es.addEventListener('node_complete', e => console.log(JSON.parse(e.data)));
        es.addEventListener('pipeline_complete', e => setDone(true));
        es.addEventListener('pipeline_error', e => setError(JSON.parse(e.data)));
        es.addEventListener('done', () => es.close());

    Events emitted:
        pipeline_start    → { message, meals, people }
        node_complete     → { node, message }
        pipeline_complete → { message, stats, pantry_skipped, pantry_restock }
        pipeline_error    → { message }
        done              → {} (stream closed)
    """
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
    """
    Intelligently normalize pantry units.
    Catches common mistakes like spices saved as kg instead of g.
    Rules:
    - Spices > 10 kg → convert to g (no one has 10kg of a spice)
    - Oils > 50 l → convert to ml
    - threshold > quantity → set threshold to 0 (clearly wrong)
    - threshold == quantity → set threshold to 10% of quantity
    """
    q, u, t = quantity, unit.lower(), restock_threshold

    # Convert suspiciously large spice quantities from kg to g
    if category in ("spice",) and u == "kg" and q > 1:
        q = q * 1000
        t = t * 1000 if t > 0 else t
        u = "g"

    # Convert suspiciously large oil quantities from l to ml
    if category in ("oil",) and u == "l" and q > 20:
        q = q * 1000
        t = t * 1000 if t > 0 else t
        u = "ml"

    # If threshold > quantity, it's clearly wrong — disable it
    if t > 0 and t >= q:
        t = 0

    return {"quantity": round(q, 2), "unit": u, "restock_threshold": round(t, 2)}

# ─────────────────────────────────────────
# ── PANTRY ENDPOINTS ──
# ─────────────────────────────────────────

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
    # Check for duplicate
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


# ─────────────────────────────────────────
# ── CONFIG ENDPOINTS ──
# ─────────────────────────────────────────

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
        "updated_at":    config.updated_at.isoformat() if config.updated_at else None,
        "onboarding_complete": config.onboarding_complete
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
    if request.onboarding_complete is not None:
        config.onboarding_complete = request.onboarding_complete

    db.commit()

    return {
        "user_id":       user_id,
        "active_stores": config.active_stores,
        "num_people":    config.num_people,
        "message":       "Config updated"
    }


# ─────────────────────────────────────────
# ── STORE PREFERENCES ENDPOINTS ──
# ─────────────────────────────────────────

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
    """
    Set or update a routing preference.
    Example: ingredient_pattern='basmati rice', preferred_store='costco'
    """
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
    """
    One-time fix — normalizes all pantry items with bad units.
    Safe to call multiple times.
    """
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

# ─────────────────────────────────────────
# ── RECIPE ENDPOINTS ──
# ─────────────────────────────────────────

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
    """
    Save a new recipe.
    Body: { name, servings, ingredients: [{name, quantity, unit, category}] }
    """
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



# ─────────────────────────────────────────
# ── ITEM REMOVAL / FEEDBACK ──
# ─────────────────────────────────────────

@app.post("/api/plan/{plan_id}/remove-item")
def remove_item(
    plan_id:  str,
    request:  dict,
    db:       Session = Depends(get_db),
    user_id:  str     = Depends(get_current_user)
):
    """
    Remove an item from the grocery list and process the reason.
    Body: { ingredient_name, meal_name, reason, store, quantity, unit }
    """
    ingredient_name = request.get("ingredient_name", "").strip()
    reason          = request.get("reason", "").strip()

    if not ingredient_name:
        raise HTTPException(status_code=400, detail="ingredient_name is required")
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    # Verify plan belongs to user
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
    """View all feedback records — useful for debugging / transparency."""
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



# ─────────────────────────────────────────
# ── INTENT PARSER ──
# ─────────────────────────────────────────

@app.post("/api/parse-intent")
def parse_intent(
    request: dict,
    db:      Session = Depends(get_db),
    user_id: str     = Depends(get_current_user)
):
    """
    Tool-calling agent for conversational plan building.
    Body: {
      message: str,
      current_state: { meals, extra_items, active_stores, num_people },
      conversation_history: [{ role, content }]
    }
    Returns: {
      state: updated plan state,
      actions: list of tools called,
      status: "clarifying" | "confirming" | "ready" | "out_of_scope",
      message: str
    }
    """
    import json
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from langchain_core.tools import tool
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    message       = request.get("message", "").strip()
    current_state = request.get("current_state", {})
    history       = request.get("conversation_history", [])

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    config       = get_or_create_user_config(user_id, db)
    known_stores = config.active_stores or ["trader_joes", "costco", "indian_store", "target"]

    # ── Mutable plan state the tools will modify ──
    plan = {
        "meals":         list(current_state.get("meals", [])),
        "extra_items":   list(current_state.get("extra_items", [])),
        "active_stores": list(current_state.get("active_stores", known_stores)),
        "num_people":    current_state.get("num_people"),
        "meal_hints":    list(current_state.get("meal_hints", [])),
        "preferences":   list(current_state.get("preferences", [])),
    }
    actions  = []
    status   = ["clarifying"]

    # ── Tools ──
    @tool
    def add_meal(name: str) -> str:
        """Add a meal to the plan. Fix any typos and use proper capitalisation."""
        clean = name.strip().title()
        if clean not in plan["meals"]:
            plan["meals"].append(clean)
            actions.append(f"Added meal: {clean}")
        return f"Added {clean}"

    @tool
    def remove_meal(name: str) -> str:
        """Remove a meal from the plan."""
        plan["meals"] = [m for m in plan["meals"] if m.lower() != name.lower()]
        actions.append(f"Removed meal: {name}")
        return f"Removed {name}"

    @tool
    def set_people(count: int) -> str:
        """Set the number of people to cook for."""
        plan["num_people"] = count
        actions.append(f"Set people: {count}")
        return f"Set to {count} people"

    @tool
    def add_extra_item(name: str) -> str:
        """Add a non-food extra item (medicine, supplement, household)."""
        clean = name.strip()
        if clean not in plan["extra_items"]:
            plan["extra_items"].append(clean)
            actions.append(f"Added extra: {clean}")
        return f"Added {clean} to extras"

    @tool
    def remove_extra_item(name: str) -> str:
        """Remove an extra item from the plan."""
        plan["extra_items"] = [x for x in plan["extra_items"] if x.lower() != name.lower()]
        actions.append(f"Removed extra: {name}")
        return f"Removed {name}"

    @tool
    def add_store(store_name: str) -> str:
        """Add a store to the active stores list. Normalise name to snake_case."""
        store_id = store_name.lower().strip().replace(" ", "_").replace("'", "")
        if store_id not in plan["active_stores"]:
            plan["active_stores"].append(store_id)
            actions.append(f"Added store: {store_id}")
            # Also save to user preferences in DB
            try:
                existing = db.query(StorePreference).filter(
                    StorePreference.user_id == user_id,
                    StorePreference.ingredient_pattern == store_id
                ).first()
                if not existing:
                    config.active_stores = plan["active_stores"]
                    db.commit()
            except:
                pass
        return f"Added store: {store_id}"

    @tool
    def remove_store(store_name: str) -> str:
        """Remove a store from the active stores list."""
        store_id = store_name.lower().strip().replace(" ", "_").replace("'", "")
        plan["active_stores"] = [s for s in plan["active_stores"] if s != store_id]
        actions.append(f"Removed store: {store_id}")
        return f"Removed {store_id}"

    @tool
    def update_pantry(ingredient: str, quantity: float, unit: str) -> str:
        """Add or update a pantry item. Use when user says they already have something."""
        try:
            existing = db.query(Pantry).filter(
                Pantry.user_id == user_id,
                Pantry.ingredient_name.ilike(ingredient)
            ).first()
            if existing:
                existing.quantity += quantity
            else:
                db.add(Pantry(
                    user_id=user_id,
                    ingredient_name=ingredient.lower(),
                    quantity=quantity,
                    unit=unit,
                    category="other",
                    restock_threshold=0
                ))
            db.commit()
            actions.append(f"Updated pantry: {ingredient} {quantity}{unit}")
            return f"Added {ingredient} to pantry"
        except Exception as e:
            return f"Could not update pantry: {str(e)}"

    @tool
    def add_meal_hint(meal: str, ingredient: str, store: str) -> str:
        """Use when user says they get a specific ingredient from a specific store for a meal.
        e.g. 'I get idli batter from Idli Express'"""
        store_id = store.lower().strip().replace(" ", "_").replace("'", "")
        plan["meal_hints"].append({"meal": meal, "ingredient": ingredient, "store": store_id})
        if store_id not in plan["active_stores"]:
            plan["active_stores"].append(store_id)
        actions.append(f"Meal hint: {meal} → {ingredient} from {store_id}")
        return f"Noted — will get {ingredient} from {store_id} for {meal}"

    @tool
    def add_preference(preference: str) -> str:
        """Add a cooking preference or dietary note. e.g. vegetarian, spicy, no onion."""
        plan["preferences"].append(preference)
        actions.append(f"Preference: {preference}")
        return f"Noted: {preference}"

    @tool
    def confirm_plan() -> str:
        """Call this when the user confirms they are happy with the plan and want to build the list."""
        status[0] = "ready"
        actions.append("User confirmed plan")
        return "Plan confirmed — building list"

    @tool
    def out_of_scope(reason: str) -> str:
        """Call this when the user asks for something completely unrelated to grocery planning."""
        status[0] = "out_of_scope"
        return reason

    tools = [
        add_meal, remove_meal, set_people,
        add_extra_item, remove_extra_item,
        add_store, remove_store,
        update_pantry, add_meal_hint,
        add_preference, confirm_plan, out_of_scope
    ]

    # ── System prompt ──
    system = f"""You are a smart grocery planning assistant. Help the user build their weekly grocery plan through natural conversation.

CURRENT PLAN:
- Meals: {json.dumps(plan["meals"])}
- Extras: {json.dumps(plan["extra_items"])}
- Stores: {json.dumps(plan["active_stores"])}
- People: {plan["num_people"]}
- Preferences: {json.dumps(plan["preferences"])}

USER'S SAVED STORES: {json.dumps(known_stores)}

Use your tools to update the plan based on what the user says. You can call multiple tools in one turn.

GUIDELINES:
- Fix typos intelligently: "paner" → "Paneer", "butter chiken" → "Butter Chicken", "idly" → "Idli"
- "I have all the spices" → call update_pantry for common spices with high quantity
- "I already have chicken" → call update_pantry("chicken", 500, "g")
- "get batter from Idli Express" → call add_meal_hint
- "I'm vegetarian" → call add_preference("vegetarian")
- "make it spicy" → call add_preference("spicy")
- "same stores as usual" → use saved stores, no change needed
- Out of scope (furniture, clothes, electronics) → call out_of_scope
- After calling tools, determine if anything is still missing:
  - No meals → ask what they want to cook
  - No num_people → ask how many people
  - Both set → move toward confirming
- When user says "yes", "looks good", "go ahead", "build it" → call confirm_plan()

After using tools, respond naturally and conversationally. Don't list the tools you called.
"""

    try:
        llm    = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent         = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)

        chat_history = []
        for h in history:
            if not isinstance(h, dict):
                continue
            role, content = h.get("role"), h.get("content") or ""
            if role == "user":
                chat_history.append(HumanMessage(content=content))
            elif role == "assistant":
                chat_history.append(AIMessage(content=content))

        result = agent_executor.invoke({
            "input":        message,
            "chat_history": chat_history,
        })

        response_text = result.get("output", "")

        # Determine status
        if status[0] == "ready":
            final_status = "ready"
        elif status[0] == "out_of_scope":
            final_status = "out_of_scope"
        elif plan["meals"] and plan["num_people"]:
            final_status = "confirming"
        else:
            final_status = "clarifying"

        # Ensure stores default if empty
        if not plan["active_stores"]:
            plan["active_stores"] = known_stores

        return {
            "state":   plan,
            "actions": actions,
            "status":  final_status,
            "message": response_text,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent failed: {str(e)}")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_ok = True
    except:
        db_ok = False
    return {
        "status":  "ok" if db_ok else "degraded",
        "db":      "connected" if db_ok else "disconnected",
        "version": "1.0.0"
    }


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
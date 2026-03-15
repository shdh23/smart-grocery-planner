"""
test_graph.py

End-to-end integration test for the full LangGraph pipeline.
Tests all nodes: recipe → consolidation → pantry_checker → store_router_food
                         extra_items → fsa_checker → store_router_extra
                         → output_formatter

Run from backend/:
    python test_graph.py

Make sure your .env has:
    OPENAI_API_KEY=sk-...
    TAVILY_API_KEY=tvly-...
    DATABASE_URL=postgresql://...
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()

from models.state import GroceryState
from graph.graph import grocery_graph


# ─────────────────────────────────────────
# PRINT HELPERS
# ─────────────────────────────────────────

def divider(char="─", width=60):
    print(char * width)

def print_section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}\n")

def print_grocery_list(final_output: dict):
    grocery_lists = final_output.get("grocery_lists",    [])
    pantry_skipped= final_output.get("pantry_skipped",   [])
    pantry_restock= final_output.get("pantry_restock",   [])
    fsa_summary   = final_output.get("fsa_summary",      [])
    needs_input   = final_output.get("needs_user_input", [])
    deductions    = final_output.get("pantry_deductions",[])
    stats         = final_output.get("stats",            {})

    # ── Stats banner ──
    print(f"  📊 {stats.get('total_stores',0)} stores  |  "
          f"{stats.get('food_count',0)} food items  |  "
          f"{stats.get('extra_count',0)} extra items  |  "
          f"💊 {stats.get('fsa_count',0)} FSA eligible  |  "
          f"🥫 {stats.get('pantry_skipped',0)} from pantry\n")

    # ── Per store ──
    for store_data in grocery_lists:
        store       = store_data["store"].upper().replace("_"," ")
        food_items  = store_data["food_items"]
        extra_items = store_data["extra_items"]

        # skip pantry_meta rows in display
        if store_data["store"] == "pantry_meta":
            continue

        print(f"  📍 {store}")
        divider()

        if food_items:
            print(f"  🍽️  Food items:")
            for item in food_items:
                qty_str = f"{item['quantity']} {item['unit']}" if item['quantity'] > 0 else "✅ in pantry"
                print(f"     {item['name']:<32} {qty_str}")
                if item.get("notes"):
                    print(f"     {'':32}  ↳ {item['notes']}")

        if extra_items:
            print(f"  🛍️  Extra items:")
            for item in extra_items:
                fsa_badge = " 💊" if item["fsa_eligible"] else ""
                print(f"     {item['name']:<32}{fsa_badge}")
                if item.get("notes"):
                    print(f"     {'':32}  ↳ {item['notes']}")
        print()

    # ── Pantry skipped ──
    if pantry_skipped:
        print(f"  🥫 Skipped — already in pantry ({len(pantry_skipped)})")
        divider()
        for name in pantry_skipped:
            print(f"  ✅ {name}")
        print()

    # ── Restock alerts ──
    if pantry_restock:
        print(f"  ⚠️  Restock after this week ({len(pantry_restock)})")
        divider()
        for item in pantry_restock:
            if item["status"] == "low_after_use":
                print(f"  🔴 {item['name']}: will have {item['will_remain']}"
                      f"{item['unit']} left "
                      f"(threshold: {item['threshold']}{item['unit']})")
            else:
                print(f"  🟡 {item['name']}: only had {item['have']}{item['unit']}, "
                      f"bought {item['to_buy']}{item['unit']} more")
            if item.get("preferred_store"):
                print(f"     💡 Restock from: {item['preferred_store']}")
        print()

    # ── FSA summary ──
    if fsa_summary:
        print(f"  💊 FSA/HSA Eligible ({len(fsa_summary)})")
        divider()
        for item in fsa_summary:
            print(f"  • {item['name']} → {item['store'].replace('_',' ')}")
            if item.get("notes"):
                print(f"    {item['notes']}")
        print()

    # ── Needs user input ──
    if needs_input:
        print(f"  ⚠️  Action Needed ({len(needs_input)} unavailable items)")
        divider()
        for item in needs_input:
            print(f"  ❌ {item['name']}")
            print(f"     Reason: {item.get('unavailable_reason','N/A')}")
            if item.get("alternatives"):
                print(f"     💡 {item['alternatives']}")
        print()

    # ── Pending pantry deductions ──
    if deductions:
        print(f"  🥫 Pantry deductions (pending your confirmation)")
        divider()
        print(f"  Type 'looks good' via POST /api/plan/{{id}}/confirm to apply.\n")
        for d in deductions:
            print(f"  - {d['ingredient_name']}: "
                  f"deduct {d['deduct_amount']} {d['unit']} → "
                  f"{d['remaining']}{d['remaining_unit']} remaining")
        print()


# ─────────────────────────────────────────
# TEST RUNNER
# ─────────────────────────────────────────

def run_test(name: str, state: GroceryState) -> GroceryState:
    print_section(f"TEST: {name}")
    print(f"  Meals:        {state['meals']}")
    print(f"  Extra items:  {state['extra_items']}")
    print(f"  People:       {state['num_people']}")
    print(f"  Stores:       {state['active_stores']}\n")

    result = grocery_graph.invoke(state)

    if result.get("error") and not result.get("routed_food") and not result.get("routed_extra"):
        print(f"  ❌ Pipeline failed: {result['error']}")
        return result

    print_grocery_list(result["final_output"])

    # ── Intermediate state checks ──
    print_section("INTERMEDIATE STATE CHECKS")
    print(f"  raw_ingredients:   {len(result.get('raw_ingredients', []))} items")
    print(f"  consolidated:      {len(result.get('consolidated', []))} items")
    print(f"  extra_ingredients: {len(result.get('extra_ingredients', []))} items")
    print(f"  fsa_flagged:       {result.get('fsa_flagged', [])}")
    print(f"  pantry_sufficient: {result.get('pantry_sufficient', [])}")
    print(f"  pantry_low:        {len(result.get('pantry_low', []))} items")
    print(f"  routed_food stores:{list(result.get('routed_food', {}).keys())}")
    print(f"  routed_extra stores:{list(result.get('routed_extra', {}).keys())}")
    print(f"  needs_user_input:  {len(result.get('needs_user_input', []))} items")
    print(f"  error:             {result.get('error')}")

    return result


# ─────────────────────────────────────────
# EMPTY STATE TEMPLATE
# Copy this for each scenario
# ─────────────────────────────────────────

def make_state(
    meals:         list[str],
    extra_items:   list[str],
    num_people:    int,
    active_stores: list[str],
    user_id:       str = "default_user"
) -> GroceryState:
    return {
        "meals":             meals,
        "extra_items":       extra_items,
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
        "final_output":      {},
        "error":             None
    }


# ─────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────

# ── SCENARIO 1 ──
# Full pipeline: Indian + Italian meals, extra items, all stores
# Pantry has garam masala, turmeric, olive oil, basmati rice, toor dal
# Expect: spices/oils skipped or reduced, restock alerts possible
SCENARIO_1 = make_state(
    meals        = ["Butter Chicken", "Pasta Primavera"],
    extra_items  = ["grapefruit face wash for acne", "vitamin D3 supplements", "ibuprofen 200mg"],
    num_people   = 4,
    active_stores= ["trader_joes", "costco", "indian_store", "target"]
)

# ── SCENARIO 2 ──
# No extra items — extra flow should be skipped entirely
SCENARIO_2 = make_state(
    meals        = ["Tacos", "Greek Salad"],
    extra_items  = [],
    num_people   = 2,
    active_stores= ["trader_joes", "target"]
)

# ── SCENARIO 3 ──
# Indian store disabled — paneer/spices should land in needs_user_input
SCENARIO_3 = make_state(
    meals        = ["Palak Paneer", "Dal Tadka"],
    extra_items  = ["SPF 50 sunscreen"],
    num_people   = 2,
    active_stores= ["trader_joes", "target"]   # no indian_store, no costco
)

# ── SCENARIO 4 ──
# Heavy pantry usage — most ingredients should come from pantry
# basmati rice (2000g in pantry), toor dal (500g), garam masala, turmeric, olive oil
SCENARIO_4 = make_state(
    meals        = ["Dal Tadka", "Jeera Rice"],
    extra_items  = [],
    num_people   = 2,
    active_stores= ["trader_joes", "costco", "indian_store", "target"]
)


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Smart Grocery Planner — End-to-End Pipeline Test")
    print("Makes real LLM + Tavily + DB calls.")
    print("Expected runtime: 60–120 seconds per scenario.\n")

    # ── Run one scenario at a time to keep output readable ──
    # Uncomment the ones you want to test

    result = run_test(
        "Scenario 1 — Full pipeline: Indian + Italian, all stores, extra items",
        SCENARIO_1
    )

    # result = run_test(
    #     "Scenario 2 — No extra items, extra flow should be skipped",
    #     SCENARIO_2
    # )

    # result = run_test(
    #     "Scenario 3 — Indian store disabled, paneer should be unavailable",
    #     SCENARIO_3
    # )

    # result = run_test(
    #     "Scenario 4 — Heavy pantry usage, most items should be covered",
    #     SCENARIO_4
    # )

    # ── Dump full state for debugging (uncomment if needed) ──
    # print_section("FULL STATE DUMP")
    # debug = {k: v for k, v in result.items() if k not in ("final_output", "raw_ingredients")}
    # print(json.dumps(debug, indent=2, default=str))

    print("\n✅ Test complete.\n")
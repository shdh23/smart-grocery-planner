import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from models.schemas import Ingredient
from models.state import GroceryState
from db.connection import SessionLocal
from db.models import Recipe, UserFeedback


class MealIngredients(BaseModel):
    meal_name:   str
    ingredients: list[Ingredient]

class RecipeAgentOutput(BaseModel):
    meals: list[MealIngredients] = Field(
        description="List of meals, each with their ingredients"
    )


RECIPE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a professional chef and nutritionist.
Your job is to extract a precise ingredient list for each meal provided.

Rules:
- Scale ALL quantities for exactly {num_people} people
- Be specific with categories: produce, dairy, meat, seafood, grain,
  spice, oil, sauce, legume, frozen, bakery, snack, beverage, household
- For Indian dishes, use authentic ingredient names (e.g. "garam masala" not "spice mix")
- Include ALL ingredients needed to cook the dish from scratch
- Do not include cooking equipment or water

UNIT RULES — think like a real cook, use the most natural unit for each ingredient:
- Dry spices and powders (turmeric, cumin, coriander, garam masala, chili powder, pepper, cardamom etc.)
  → ALWAYS use "tsp" for small amounts or "g" for larger amounts. NEVER use "ml" for dry ingredients.
  → Example: turmeric powder: 1 tsp, garam masala: 2 tsp, salt: 1 tsp
- Liquid ingredients (oil, cream, milk, coconut milk, sauces, vinegar) → use "ml"
- Whole items (onions, garlic cloves, eggs, tomatoes, green chilies, lemons) → use "pieces"
- Produce by weight (spinach, chicken, paneer, cheese, meat) → use "g" or "kg"
- Butter and ghee → use "g" or "tbsp"
- Fresh herbs (cilantro, basil, mint) → use "g" or "tbsp"
- Grains, lentils, flour → use "g" or "cups"

SELF-CHECK before responding: Look at each ingredient you have listed.
Ask yourself: "Would a real cook measure this in ml?" 
If it is a powder or dry spice and you used ml, CORRECT IT to tsp or g.

EXCLUSIONS — never include these ingredients (user has removed them before):
{exclusions}

STORE-SOURCED ITEMS (user is getting these from a specific store — do NOT list them or their from-scratch ingredients):
{store_sourced_instructions}

{format_instructions}"""
    ),
    ("human", """Extract ingredients for these meals: {meals}

IMPORTANT: Some meal names may contain user instructions after a dash or in parentheses.
Examples:
  "Idli - I get batter from Idli Express" → ingredient: idli batter, preferred_store: idly_express
  "Pasta (use store-bought sauce from Trader Joes)" → ingredient: pasta sauce, preferred_store: trader_joes
  "Dal Tadka - I use MDH masala from indian store" → note MDH masala routed to indian_store

When you see such instructions:
1. Extract the simplified ingredient they describe
2. Set the ingredient's notes field to: "get from <store_name>" so the store router knows where to route it
3. Skip ingredients they say they make themselves or don't need
4. If they mention a new store not in the active stores list, still note it — the store router will handle it""")
])


def lookup_saved_recipe(user_id: str, meal_name: str, num_people: int) -> list[Ingredient] | None:
    """If we have a saved recipe for this meal, scale to num_people and return; else None."""
    try:
        db = SessionLocal()
        # Case-insensitive match
        recipe = db.query(Recipe).filter(
            Recipe.user_id == user_id,
            Recipe.name.ilike(meal_name.strip())
        ).first()
        db.close()

        if not recipe:
            return None

        print(f"  Saved recipe for '{meal_name}' (scale {recipe.servings} -> {num_people})")

        scale = num_people / recipe.servings
        ingredients = []
        for item in recipe.ingredients:
            ing = Ingredient(
                name=       item["name"],
                quantity=   round(item["quantity"] * scale, 2),
                unit=       item["unit"],
                category=   item["category"],
                notes=      f"for {meal_name} (your recipe)",
            )
            ingredients.append(ing)
        return ingredients

    except Exception as e:
        print(f"  Recipe lookup failed: {e}")
        return None



def get_ingredient_exclusions(user_id: str, meal_name: str) -> list[str]:
    """Ingredients to skip for this meal from user feedback (meal-specific + global skip)."""
    try:
        db = SessionLocal()
        records = db.query(UserFeedback).filter(
            UserFeedback.user_id == user_id,
            UserFeedback.action_taken.in_(["SKIP_FOR_MEAL", "SKIP_ALWAYS"]),
            db.query(UserFeedback).filter(
                (UserFeedback.meal_name.ilike(meal_name)) |
                (UserFeedback.meal_name == None)
            ).exists()
        ).all()

        # Simpler approach — two separate queries
        meal_skips = db.query(UserFeedback.ingredient_name).filter(
            UserFeedback.user_id == user_id,
            UserFeedback.action_taken == "SKIP_FOR_MEAL",
            UserFeedback.meal_name.ilike(meal_name)
        ).all()

        global_skips = db.query(UserFeedback.ingredient_name).filter(
            UserFeedback.user_id == user_id,
            UserFeedback.action_taken == "SKIP_ALWAYS",
            UserFeedback.meal_name == None
        ).all()

        db.close()

        exclusions = list(set(
            [r.ingredient_name for r in meal_skips] +
            [r.ingredient_name for r in global_skips]
        ))
        return exclusions

    except Exception as e:
        print(f"  Feedback lookup failed: {e}")
        return []


DRY_SPICE_KEYWORDS = {
    "powder", "masala", "turmeric", "cumin", "coriander", "chili", "chilli",
    "pepper", "paprika", "cardamom", "cinnamon", "clove", "nutmeg", "fenugreek",
    "methi", "ajwain", "asafoetida", "hing", "salt", "sugar", "flour",
    "garam", "tandoori", "chat", "chaat", "amchur", "kasuri"
}

def fix_units(ingredients: list) -> list:
    """Fallback: if LLM returned dry spice in ml, convert to tsp. Prompt handles the rest."""
    for ing in ingredients:
        name_lower = ing.name.lower()
        unit_lower = (ing.unit or "").lower()
        if unit_lower == "ml" and any(kw in name_lower for kw in DRY_SPICE_KEYWORDS):
            ing.quantity = round(ing.quantity / 5, 1)
            ing.unit     = "tsp"
            print(f"  Unit corrected: {ing.name} ml -> tsp")
    return ingredients

def recipe_agent(state: GroceryState) -> dict:
    """Use saved recipes first, then LLM for the rest. Returns only raw_ingredients."""
    print(f"RecipeAgent: {len(state['meals'])} meals, {state['num_people']} people")

    user_id    = state.get("user_id", "default_user")
    num_people = state["num_people"]

    saved_results: list[tuple[str, list[Ingredient]]] = []
    llm_meals:     list[str]                          = []
    meal_hints     = {h["meal"]: h for h in state.get("meal_hints", [])}

    for meal in state["meals"]:
        saved = lookup_saved_recipe(user_id, meal, num_people)
        if saved:
            saved_results.append((meal, saved))
            continue

        hint = meal_hints.get(meal)
        if hint and hint.get("skip_llm") and hint.get("ingredients"):
            print(f"  Using hint for '{meal}': {hint['ingredients']} from {hint.get('store', 'unknown')}")
            hint_ingredients = []
            for ing_name in hint["ingredients"]:
                hint_ingredients.append(Ingredient(
                    name=     ing_name,
                    quantity= 1.0,
                    unit=     "pieces",
                    category= "other",
                    store=    hint.get("store"),
                    notes=    f"for {meal} (your instruction)"
                ))
            saved_results.append((meal, hint_ingredients))
            continue

        llm_meals.append(meal)

    raw_ingredients: list[Ingredient] = []

    for meal_name, ingredients in saved_results:
        raw_ingredients.extend(fix_units(ingredients))

    if llm_meals:
        try:
            parser = PydanticOutputParser(pydantic_object=RecipeAgentOutput)
            llm    = ChatOpenAI(model="gpt-4o", temperature=0,
                                api_key=os.getenv("OPENAI_API_KEY"))
            chain  = RECIPE_PROMPT | llm | parser

            exclusion_notes = []
            for meal in llm_meals:
                excls = get_ingredient_exclusions(user_id, meal)
                if excls:
                    exclusion_notes.append(f"For {meal}, do NOT include: {', '.join(excls)}")
            exclusion_str = "\n".join(exclusion_notes) if exclusion_notes else "None"

            overrides = state.get("item_store_overrides") or {}
            store_sourced_parts = []
            for item_name, store_slug in overrides.items():
                item_lower = item_name.lower()
                if "idly" in item_lower or "idli" in item_lower or "batter" in item_lower:
                    store_sourced_parts.append(
                        "For Idli/Idly: the user is getting 'idly batter' from a store. "
                        "Do NOT list rice, urad dal, fenugreek seeds, or any ingredient used only to make the batter. "
                        "ONLY list accompaniments: chutney ingredients (coconut, cilantro, green chili, ginger, etc.), "
                        "sambar ingredients if applicable, and any other sides."
                    )
                else:
                    store_sourced_parts.append(f"The user is getting '{item_name}' from {store_slug}. Do not list ingredients that are only for making '{item_name}'.")
            store_sourced_str = "\n".join(store_sourced_parts) if store_sourced_parts else "None"

            result: RecipeAgentOutput = chain.invoke({
                "meals":                    ", ".join(llm_meals),
                "num_people":               num_people,
                "format_instructions":      parser.get_format_instructions(),
                "exclusions":               exclusion_str,
                "store_sourced_instructions": store_sourced_str,
            })

            for meal in result.meals:
                fixed = fix_units(meal.ingredients)
                for ingredient in fixed:
                    ingredient.notes = f"for {meal.meal_name}"
                    raw_ingredients.append(ingredient)

            print(f"  LLM extracted: {', '.join(llm_meals)}")

        except Exception as e:
            print(f"RecipeAgent LLM failed: {e}")
            return {"raw_ingredients": raw_ingredients, "error": f"RecipeAgent failed: {str(e)}"}

    print(f"RecipeAgent done: {len(raw_ingredients)} ingredients (saved: {len(saved_results)}, LLM: {len(llm_meals)})")

    return {"raw_ingredients": raw_ingredients}
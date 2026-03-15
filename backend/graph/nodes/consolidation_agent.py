from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from models.schemas import Ingredient
from models.state import GroceryState
import os


class ConsolidationOutput(BaseModel):
    consolidated_ingredients: list[Ingredient] = Field(
        description="Deduplicated and merged ingredient list"
    )


CONSOLIDATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a precise grocery list optimizer.
You will receive a raw ingredient list extracted from multiple meals.
Your job is to deduplicate and merge it into one clean shopping list.

Rules:
- Merge ingredients with the same name into one entry with summed quantities
- Normalize units before summing:
    * Convert all weights to grams (1kg=1000g, 1oz=28g, 1lb=454g)
    * Convert all volumes to ml (1l=1000ml, 1cup=240ml, 1tbsp=15ml, 1tsp=5ml)
    * Exception: keep "pieces" and "pinch" as-is
- After summing, convert back to the most human-readable unit:
    * >= 1000g → kg
    * >= 1000ml → l
- Keep the most specific category if two entries differ
- In the notes field, list ALL meals this ingredient is used in
- Do NOT drop any ingredient

PANTRY-FRIENDLY UNITS (critical for matching user's pantry):
The system compares your output to the user's pantry (stored in standard units).
Use units that match how pantries are typically stored so the system can correctly
mark "already in pantry" vs "need to buy". Follow these conventions:

- Dry goods → ALWAYS output in "g" or "kg" (never tsp/tbsp/cups/ml for these):
  * All spices and powders (turmeric, cumin, coriander, garam masala, chili powder,
    salt, pepper, cardamom, cinnamon, fenugreek, methi, paprika, etc.)
    Convert from tsp/tbsp using ~2.5g per tsp for ground spices, ~7.5g per tbsp.
  * Flour, sugar, rice, pasta, grains, lentils, beans, nuts
  * Use g for amounts under 1000g, kg for 1000g and above

- Liquids → output in "ml" or "l":
  * Oil, cream, milk, water, vinegar, honey, sauces
  * Convert from cups/tbsp/tsp: 1 cup=240ml, 1 tbsp=15ml, 1 tsp=5ml
  * Use ml for amounts under 1000ml, l for 1000ml and above

- Countable items → use "pieces" (or "piece"):
  * Eggs, onions, garlic cloves, tomatoes, lemons, potatoes, etc.

- Butter and ghee → use "g" (density ~1g/ml if given in volume)

- Fresh herbs (cilantro, basil, mint) and produce by weight → use "g" or "kg"

Never output dry spices or flour/sugar/grains in tsp, tbsp, cups, or ml — always g or kg.
Never output liquids in tsp/tbsp/cups when the user stores them in ml — use ml or l.

{format_instructions}"""
    ),
    ("human", "Here is the raw ingredient list to consolidate:\n\n{raw_ingredients}")
])


# same dry-spice fix as recipe_agent
DRY_SPICE_KEYWORDS = {
    "powder", "masala", "turmeric", "cumin", "coriander", "chili", "chilli",
    "pepper", "paprika", "cardamom", "cinnamon", "clove", "nutmeg", "fenugreek",
    "methi", "ajwain", "asafoetida", "hing", "salt", "sugar", "flour",
    "garam", "tandoori", "chat", "chaat", "amchur", "kasuri"
}

def fix_units(ingredients: list) -> list:
    corrected = []
    for ing in ingredients:
        name_lower = ing.name.lower()
        unit_lower = (ing.unit or "").lower()
        if unit_lower == "ml" and any(kw in name_lower for kw in DRY_SPICE_KEYWORDS):
            ing.quantity = round(ing.quantity / 5, 1)
            ing.unit = "tsp"
        if unit_lower == "ml" and any(kw in name_lower for kw in ["butter", "ghee"]):
            ing.unit = "g"
        corrected.append(ing)
    return corrected


def consolidation_agent(state: GroceryState) -> dict:
    """Dedupe and merge raw ingredients into one list. Returns consolidated."""
    raw = state["raw_ingredients"]
    print(f"Consolidation: merging {len(raw)} raw ingredients")

    if not raw:
        return {"consolidated": [], "error": "ConsolidationAgent: no ingredients to consolidate"}

    try:
        parser = PydanticOutputParser(pydantic_object=ConsolidationOutput)
        llm    = ChatOpenAI(model="gpt-4o", temperature=0,
                            api_key=os.getenv("OPENAI_API_KEY"))
        chain  = CONSOLIDATION_PROMPT | llm | parser

        ingredients_text = "\n".join([
            f"- {ing.name}: {ing.quantity} {ing.unit} [{ing.category}] {ing.notes or ''}"
            for ing in raw
        ])

        result: ConsolidationOutput = chain.invoke({
            "raw_ingredients":     ingredients_text,
            "format_instructions": parser.get_format_instructions()
        })

        consolidated = fix_units(result.consolidated_ingredients)
        print(f"Consolidation done: {len(consolidated)} unique (removed {len(raw) - len(consolidated)} dupes)")

        return {"consolidated": consolidated}

    except Exception as e:
        print(f"Consolidation failed: {e}")
        return {"consolidated": fix_units(raw)}
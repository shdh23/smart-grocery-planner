from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from models.schemas import Ingredient
from models.state import GroceryState
import os


class ExtraItemsOutput(BaseModel):
    items: list[Ingredient] = Field(
        description="Structured list of non-food items ready for FSA checking and store routing"
    )


EXTRA_ITEMS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a shopping assistant that structures non-food items for a grocery list.

The user has provided items they want to buy that are NOT part of any recipe —
things like personal care products, medicine, vitamins, household supplies, etc.

For each item, produce a structured entry with these rules:

NAME:
- Keep the full descriptive name exactly as the user wrote it
- Do NOT simplify or shorten — specificity is critical for FSA/HSA checking later
- Good: "grapefruit face wash for acne"  Bad: "face wash"
- Good: "SPF 50 sunscreen"              Bad: "sunscreen"
- Good: "vitamin D3 2000IU supplement"  Bad: "vitamin D"

QUANTITY + UNIT:
- Default to quantity=1, unit="piece" unless the user specified otherwise

CATEGORY — must be one of:
- personal_care, medicine, supplement, baby, pet, household, other

NOTES:
- Leave empty — the FSA checker will populate this field later

{format_instructions}"""
    ),
    ("human", "Structure these extra items:\n\n{items}")
])


def extra_items_agent(state: GroceryState) -> dict:
    """Turn extra_items into structured ingredients. Returns extra_ingredients."""
    extra = state.get("extra_items", [])

    if not extra:
        print("ExtraItemsAgent: no extra items, skipping")
        return {"extra_ingredients": []}

    print(f"ExtraItemsAgent: structuring {len(extra)} extra items")

    try:
        parser = PydanticOutputParser(pydantic_object=ExtraItemsOutput)
        llm    = ChatOpenAI(model="gpt-4o", temperature=0,
                            api_key=os.getenv("OPENAI_API_KEY"))
        chain  = EXTRA_ITEMS_PROMPT | llm | parser

        result: ExtraItemsOutput = chain.invoke({
            "items":               "\n".join(f"- {item}" for item in extra),
            "format_instructions": parser.get_format_instructions()
        })

        print(f"ExtraItemsAgent: structured {len(result.items)} items")
        for item in result.items:
            print(f"  {item.name} [{item.category}]")

        return {"extra_ingredients": result.items}

    except Exception as e:
        print(f"ExtraItemsAgent failed: {e}")
        return {"extra_ingredients": []}
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.schemas import Ingredient
from models.state import GroceryState
from db.connection import SessionLocal
from db.models import StorePreference
from typing import Optional
import os


class RoutedIngredient(BaseModel):
    name:               str
    quantity:           float
    unit:               str
    category:           str
    notes:              Optional[str] = None
    assigned_store:     Optional[str] = Field(None)
    available:          bool
    unavailable_reason: Optional[str] = None
    alternatives:       Optional[str] = None

class StoreRouterOutput(BaseModel):
    routed:      list[RoutedIngredient]
    unavailable: list[RoutedIngredient]


SYSTEM_PROMPT = """You are an expert grocery shopper routing items to the
best store from the user's active stores list.

ACTIVE STORES: {active_stores}
Only assign items to stores in this list. Never suggest a disabled store.

USER'S CUSTOM PREFERENCES (always override your decisions):
{user_preferences}

You have access to a web search tool. Use it to verify whether a specific
store carries a specific item when you are not confident.

Routing rules:
1. INGREDIENT NOTES OVERRIDE — if an ingredient has a note like "get from idly_express" or "from Trader Joes", ALWAYS route it to that store, even if it is not in the active stores list. Add the store to the routing automatically.
2. AVAILABILITY FIRST — only assign a store if it actually carries the item. Search if unsure.
3. Best store priority:
   - Indian store → Indian/South Asian ingredients
   - Costco → bulk staples (large rice, oils, proteins)
   - Trader Joe's → everyday produce, dairy, packaged goods
   - Target → personal care, medicine, household, supplements
4. If not available at ANY active store → set available=false, explain why, suggest alternative
5. Batch searches to minimize tool calls

Return JSON matching this schema:
{format_instructions}"""


def load_user_preferences(user_id: str) -> str:
    db: Session = SessionLocal()
    try:
        prefs = db.query(StorePreference).filter(
            StorePreference.user_id == user_id
        ).all()
        if not prefs:
            return "None — use best judgment."
        return "\n".join([
            f"- Always buy '{p.ingredient_pattern}' from {p.preferred_store}"
            for p in prefs
        ])
    finally:
        db.close()


def group_by_store(
    routed: list[RoutedIngredient],
    fsa_flagged: list[str] = []
) -> dict[str, list[Ingredient]]:
    grouped: dict[str, list[Ingredient]] = {}
    for item in routed:
        if item.available and item.assigned_store:
            store = item.assigned_store
            if store not in grouped:
                grouped[store] = []
            grouped[store].append(Ingredient(
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                category=item.category,
                store=item.assigned_store,
                fsa_eligible=item.name in fsa_flagged if fsa_flagged else None,
                notes=item.notes
            ))
    return grouped


def build_unavailable_list(items: list[RoutedIngredient]) -> list[dict]:
    return [
        {
            "name":               item.name,
            "quantity":           item.quantity,
            "unit":               item.unit,
            "category":           item.category,
            "unavailable_reason": item.unavailable_reason,
            "alternatives":       item.alternatives,
        }
        for item in items
    ]


def _run_store_router(
    items:         list[Ingredient],
    active_stores: list[str],
    user_id:       str,
    fsa_flagged:   list[str],
    label:         str
) -> tuple[dict[str, list[Ingredient]], list[dict]]:
    if not items:
        print(f"StoreRouter ({label}): nothing to route")
        return {}, []

    items_to_route = [i for i in items if i.quantity > 0]
    if not items_to_route:
        print(f"StoreRouter ({label}): all items covered by pantry")
        return {}, []

    print(f"StoreRouter ({label}): routing {len(items_to_route)} items -> {', '.join(active_stores)}")

    user_preferences = load_user_preferences(user_id)
    parser           = PydanticOutputParser(pydantic_object=StoreRouterOutput)

    search_tool = TavilySearchResults(
        max_results=3, search_depth="basic",
        api_key=os.getenv("TAVILY_API_KEY")
    )
    tools = [search_tool]

    llm = ChatOpenAI(model="gpt-4o", temperature=0,
                     api_key=os.getenv("OPENAI_API_KEY")).bind_tools(tools)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    agent          = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=False,
        max_iterations=10, handle_parsing_errors=True
    )

    items_text = "\n".join([
        f"- {ing.name}: {ing.quantity} {ing.unit} [{ing.category}]"
        for ing in items_to_route
    ])

    response = agent_executor.invoke({
        "input":               f"Route these items to stores:\n\n{items_text}",
        "active_stores":       ", ".join(active_stores),
        "user_preferences":    user_preferences,
        "format_instructions": parser.get_format_instructions()
    })

    result: StoreRouterOutput = parser.parse(response["output"])
    routed      = group_by_store(result.routed, fsa_flagged)
    unavailable = build_unavailable_list(result.unavailable)

    total_routed = sum(len(v) for v in routed.values())
    print(f"StoreRouter ({label}): routed {total_routed} items to {len(routed)} stores")
    if unavailable:
        print(f"{len(unavailable)} items unavailable:")
        for item in unavailable:
            print(f"  - {item['name']}: {item['unavailable_reason']}")
            if item["alternatives"]:
                print(f"    alt: {item['alternatives']}")

    return routed, unavailable


def store_router_agent_food(state: GroceryState) -> dict:
    """Route food items to stores. item_store_overrides get pinned to that store first."""
    consolidated = state.get("consolidated", [])
    overrides = state.get("item_store_overrides") or {}
    active_stores = state["active_stores"]
    override_routed, to_route = _apply_item_store_overrides(consolidated, overrides, active_stores)
    try:
        routed, unavailable = _run_store_router(
            items=         to_route,
            active_stores= active_stores,
            user_id=       state["user_id"],
            fsa_flagged=   [],
            label=         "food"
        )
        for store, ing_list in override_routed.items():
            routed[store] = routed.get(store, []) + ing_list
        return {
            "routed_food":      routed,
            "needs_user_input": unavailable
        }
    except Exception as e:
        print(f"StoreRouter (food) failed: {e}")
        return {"routed_food": override_routed, "needs_user_input": []}


def _apply_item_store_overrides(
    items: list[Ingredient],
    overrides: dict[str, str],
    active_stores: list[str]
) -> tuple[dict[str, list[Ingredient]], list[Ingredient]]:
    """Send overridden items straight to their store; return (routed, rest_to_route)."""
    routed: dict[str, list[Ingredient]] = {}
    to_route: list[Ingredient] = []
    for ing in items:
        matched_store = None
        for override_item, store_slug in overrides.items():
            if override_item.lower() in ing.name.lower() or ing.name.lower() in override_item.lower():
                matched_store = store_slug
                break
        if matched_store and matched_store in active_stores:
            if matched_store not in routed:
                routed[matched_store] = []
            ing_with_store = Ingredient(
                name=ing.name, quantity=ing.quantity, unit=ing.unit,
                category=ing.category, store=matched_store, notes=ing.notes
            )
            routed[matched_store].append(ing_with_store)
            print(f"   Override: {ing.name} -> {matched_store}")
        else:
            to_route.append(ing)
    return routed, to_route


def store_router_agent_extra(state: GroceryState) -> dict:
    """Route extra items; overrides go to their store, rest via LLM."""
    extra_ingredients = state.get("extra_ingredients", [])
    overrides = state.get("item_store_overrides") or {}
    active_stores = state["active_stores"]

    override_routed, to_route = _apply_item_store_overrides(extra_ingredients, overrides, active_stores)

    try:
        routed, unavailable = _run_store_router(
            items=         to_route,
            active_stores= active_stores,
            user_id=       state["user_id"],
            fsa_flagged=   state.get("fsa_flagged", []),
            label=         "extra"
        )
        for store, ing_list in override_routed.items():
            routed[store] = routed.get(store, []) + ing_list
        existing = state.get("needs_user_input", [])
        return {
            "routed_extra":     routed,
            "needs_user_input": existing + unavailable
        }
    except Exception as e:
        print(f"StoreRouter (extra) failed: {e}")
        return {"routed_extra": override_routed}
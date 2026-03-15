from langgraph.graph import StateGraph, END, START
from models.state import GroceryState
from graph.nodes.recipe_agent import recipe_agent
from graph.nodes.extra_items_agent import extra_items_agent
from graph.nodes.consolidation_agent import consolidation_agent
from graph.nodes.pantry_checker_agent import pantry_checker_agent
from graph.nodes.fsa_checker_agent import fsa_checker_agent
from graph.nodes.store_router_agent import store_router_agent_food, store_router_agent_extra
from graph.nodes.output_formatter import output_formatter


def merge_barrier(state: GroceryState) -> dict:
    """No-op. Both store routers join here so we wait for both before output_formatter."""
    return {}


def recipe_failed(state: GroceryState) -> str:
    """Stop food flow if recipe agent failed and we have no ingredients."""
    if state.get("error") and not state.get("raw_ingredients"):
        print(f"Food flow stopping: {state['error']}")
        return "stop"
    return "continue"


def has_extra_items(state: GroceryState) -> str:
    """Skip extra flow when user didn't add any extras."""
    if not state.get("extra_items"):
        print("No extra items, skipping extra flow")
        return "skip"
    return "continue"


def build_graph() -> StateGraph:
    graph = StateGraph(GroceryState)

    graph.add_node("recipe_agent",             recipe_agent)
    graph.add_node("extra_items_agent",        extra_items_agent)
    graph.add_node("consolidation_agent",      consolidation_agent)
    graph.add_node("pantry_checker_agent",     pantry_checker_agent)
    graph.add_node("fsa_checker_agent",        fsa_checker_agent)
    graph.add_node("store_router_agent_food",  store_router_agent_food)
    graph.add_node("store_router_agent_extra", store_router_agent_extra)
    graph.add_node("output_formatter",         output_formatter)
    graph.add_node("merge_barrier",            merge_barrier)

    graph.add_edge(START, "recipe_agent")
    graph.add_edge(START, "extra_items_agent")

    graph.add_conditional_edges(
        "recipe_agent",
        recipe_failed,
        {
            "stop":     "merge_barrier",
            "continue": "consolidation_agent"
        }
    )

    graph.add_edge("consolidation_agent",     "pantry_checker_agent")
    graph.add_edge("pantry_checker_agent",    "store_router_agent_food")
    graph.add_edge("store_router_agent_food", "merge_barrier")

    # ────────────────────────────────────────
    # EXTRA ITEMS FLOW
    # START → extra_items → fsa_checker → store_router_extra → output_formatter
    # ────────────────────────────────────────

    graph.add_conditional_edges(
        "extra_items_agent",
        has_extra_items,
        {
            "skip":     "merge_barrier",
            "continue": "fsa_checker_agent"
        }
    )

    graph.add_edge("fsa_checker_agent",        "store_router_agent_extra")
    graph.add_edge("store_router_agent_extra", "merge_barrier")

    graph.add_edge("merge_barrier",    "output_formatter")
    graph.add_edge("output_formatter", END)

    return graph.compile()


grocery_graph = build_graph()
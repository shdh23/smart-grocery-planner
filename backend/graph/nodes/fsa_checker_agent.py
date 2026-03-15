from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.tools import tool
from pydantic import BaseModel, Field
from models.state import GroceryState
from typing import Optional
import os
import json


class FSAItem(BaseModel):
    name:      str
    eligible:  bool
    reason:    str
    condition: Optional[str] = None

class FSACheckerOutput(BaseModel):
    items: list[FSAItem]


SYSTEM_PROMPT = """You are an expert in FSA and HSA eligibility rules in the United States.

You have two tools: web_search and fsa_store_lookup.

Key rules:
- Items must treat, diagnose, cure, or prevent a medical condition to be eligible
- CONDITIONAL eligibility is common:
    * Sunscreen: eligible if SPF 15+ and broad spectrum
    * Face wash: eligible ONLY if treating a medical condition (e.g. acne)
    * Vitamins: eligible ONLY if prescribed by a doctor
    * Shampoo: eligible ONLY if treating dandruff
- Search for the specific product name + "FSA eligible" when unsure

For each item: set eligible, explain reason, note condition if required.

{format_instructions}"""


@tool
def fsa_store_lookup(item_name: str) -> str:
    """Look up FSA/HSA eligibility using FSA Store's database."""
    search = TavilySearchResults(max_results=2, api_key=os.getenv("TAVILY_API_KEY"))
    results = search.invoke(f"site:fsastore.com {item_name} eligible")
    return json.dumps(results) if results else f"No result found for {item_name}"


def fsa_checker_agent(state: GroceryState) -> dict:
    """Check extra_ingredients for FSA/HSA eligibility. Returns fsa_flagged + updated extra_ingredients."""
    items = state.get("extra_ingredients", [])

    if not items:
        print("FSAChecker: no extra items to check")
        return {"fsa_flagged": [], "extra_ingredients": []}

    print(f"FSAChecker: checking {len(items)} items for FSA/HSA")

    try:
        parser = PydanticOutputParser(pydantic_object=FSACheckerOutput)

        web_search_tool = TavilySearchResults(
            max_results=3, search_depth="basic",
            api_key=os.getenv("TAVILY_API_KEY")
        )
        tools = [web_search_tool, fsa_store_lookup]

        llm = ChatOpenAI(model="gpt-4o", temperature=0,
                         api_key=os.getenv("OPENAI_API_KEY")).bind_tools(tools)

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        agent          = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent, tools=tools, verbose=True,
            max_iterations=8, handle_parsing_errors=True
        )

        items_text = "\n".join([
            f"- {item.name} (category: {item.category})" for item in items
        ])

        response = agent_executor.invoke({
            "input": f"Check FSA/HSA eligibility:\n\n{items_text}",
            "format_instructions": parser.get_format_instructions()
        })

        result: FSACheckerOutput = parser.parse(response["output"])

        fsa_flagged = [item.name for item in result.items if item.eligible]

        # Annotate extra_ingredients with FSA status
        fsa_map = {item.name: item for item in result.items}
        updated_items = []
        for ingredient in items:
            if ingredient.name in fsa_map:
                fsa_result = fsa_map[ingredient.name]
                ingredient.fsa_eligible = fsa_result.eligible
                if fsa_result.eligible:
                    note = f"FSA/HSA eligible — {fsa_result.reason}"
                    if fsa_result.condition:
                        note += f" (requires: {fsa_result.condition})"
                    ingredient.notes = note
            updated_items.append(ingredient)

        print(f"FSAChecker: {len(fsa_flagged)} of {len(items)} FSA eligible")
        for item in result.items:
            status = "eligible" if item.eligible else "not eligible"
            print(f"  {item.name}: {status}")
            if item.condition:
                print(f"    condition: {item.condition}")

        return {
            "fsa_flagged":       fsa_flagged,
            "extra_ingredients": updated_items
        }

    except Exception as e:
        print(f"FSAChecker failed: {e}")
        return {"fsa_flagged": [], "extra_ingredients": items}
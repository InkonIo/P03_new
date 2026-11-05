# python, persona layer for P03 Menu Simulator (personas react independently; see mirofish_adapter.py for interacting agents)
"""
Generates 15 synthetic guest personas and simulates their reaction to a menu scenario
via LLM tool-calling (Anthropic API). Falls back to a rule-based heuristic simulator
when no ANTHROPIC_API_KEY is set, so the project runs end-to-end without a key.

AI-persona output is a qualitative signal layered on top of the econometric baseline,
not proof of real guest behavior -- per the project's own stated limitation.
"""
import json
import os
import random
from dataclasses import dataclass, asdict
from pathlib import Path

random.seed(7)

PERSONAS = [
    {"id": "P01", "name": "Budget Student", "budget_sensitivity": 0.9, "loyalty": 0.3, "prefers": ["Burgers", "Sides", "Drinks"]},
    {"id": "P02", "name": "Family with Kids", "budget_sensitivity": 0.6, "loyalty": 0.5, "prefers": ["Pizza", "Pasta", "Desserts"]},
    {"id": "P03", "name": "Health-Conscious Professional", "budget_sensitivity": 0.4, "loyalty": 0.4, "prefers": ["Salads", "Drinks"]},
    {"id": "P04", "name": "Weekend Couple", "budget_sensitivity": 0.3, "loyalty": 0.6, "prefers": ["Pizza", "Desserts", "Drinks"]},
    {"id": "P05", "name": "Loyal Regular", "budget_sensitivity": 0.3, "loyalty": 0.9, "prefers": ["Burgers", "Pasta"]},
    {"id": "P06", "name": "Price-First Commuter", "budget_sensitivity": 0.95, "loyalty": 0.2, "prefers": ["Sides", "Drinks"]},
    {"id": "P07", "name": "Foodie Explorer", "budget_sensitivity": 0.2, "loyalty": 0.3, "prefers": ["Pizza", "Pasta", "Salads"]},
    {"id": "P08", "name": "Office Lunch Group", "budget_sensitivity": 0.5, "loyalty": 0.5, "prefers": ["Burgers", "Salads", "Drinks"]},
    {"id": "P09", "name": "Late-Night Snacker", "budget_sensitivity": 0.6, "loyalty": 0.3, "prefers": ["Sides", "Burgers"]},
    {"id": "P10", "name": "Vegetarian Guest", "budget_sensitivity": 0.5, "loyalty": 0.6, "prefers": ["Salads", "Pasta"]},
    {"id": "P11", "name": "Dessert Lover", "budget_sensitivity": 0.4, "loyalty": 0.5, "prefers": ["Desserts", "Drinks"]},
    {"id": "P12", "name": "Big Spender", "budget_sensitivity": 0.1, "loyalty": 0.7, "prefers": ["Pizza", "Burgers", "Desserts"]},
    {"id": "P13", "name": "First-Time Visitor", "budget_sensitivity": 0.5, "loyalty": 0.0, "prefers": ["Pizza", "Burgers"]},
    {"id": "P14", "name": "Delivery-Only User", "budget_sensitivity": 0.7, "loyalty": 0.4, "prefers": ["Pizza", "Sides"]},
    {"id": "P15", "name": "Diet-Tracking Gym-Goer", "budget_sensitivity": 0.5, "loyalty": 0.4, "prefers": ["Salads", "Drinks"]},
]


@dataclass
class PersonaReaction:
    persona_id: str
    persona_name: str
    reaction: str  # "accept" | "switch_substitute" | "leave"
    objection: str
    switched_to_category: str | None


def _heuristic_reaction(persona: dict, category: str, price_delta_pct: float, removed: bool) -> PersonaReaction:
    """Rule-based fallback: no API key needed, deterministic given seed."""
    affinity = 1.0 if category in persona["prefers"] else 0.4
    pain = persona["budget_sensitivity"] * max(price_delta_pct, 0) * (3 - affinity)

    if removed:
        if persona["loyalty"] > 0.6 and category in persona["prefers"]:
            reaction, objection = "leave", f"{persona['name']} is upset their favorite {category} item is gone, may switch restaurants"
        else:
            reaction, objection = "switch_substitute", f"{persona['name']} picks a similar {category} item instead"
        return PersonaReaction(persona["id"], persona["name"], reaction, objection, category if reaction == "switch_substitute" else None)

    if pain > 0.12:
        if persona["loyalty"] < 0.4:
            reaction = "leave"
            objection = f"{persona['name']} sees the price hike and orders from a competitor instead"
            switched = None
        else:
            reaction = "switch_substitute"
            objection = f"{persona['name']} grumbles about the price but picks a cheaper item in the same category"
            switched = category
    else:
        reaction = "accept"
        objection = f"{persona['name']} barely notices the change, orders as usual"
        switched = None

    return PersonaReaction(persona["id"], persona["name"], reaction, objection, switched)


def simulate_personas(category: str, price_delta_pct: float = 0.0, removed: bool = False) -> list[PersonaReaction]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return [_heuristic_reaction(p, category, price_delta_pct, removed) for p in PERSONAS]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        return [_heuristic_reaction(p, category, price_delta_pct, removed) for p in PERSONAS]

    reactions = []
    change_desc = (
        f"the item was REMOVED from the menu" if removed
        else f"the price of items in category '{category}' changed by {price_delta_pct*100:+.0f}%"
    )
    for persona in PERSONAS:
        prompt = f"""You are simulating a restaurant guest persona for a what-if menu simulation.

Persona: {persona['name']}
Budget sensitivity (0=doesn't care about price, 1=very price sensitive): {persona['budget_sensitivity']}
Loyalty to this restaurant (0=none, 1=very loyal): {persona['loyalty']}
Preferred categories: {', '.join(persona['prefers'])}

Menu change: {change_desc}

React in character. Respond ONLY with JSON: {{"reaction": "accept"|"switch_substitute"|"leave", "objection": "<one sentence in character>", "switched_to_category": "<category name or null>"}}"""
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            text = text[text.find("{"):text.rfind("}") + 1]
            data = json.loads(text)
            reactions.append(PersonaReaction(
                persona["id"], persona["name"],
                data.get("reaction", "accept"), data.get("objection", ""),
                data.get("switched_to_category"),
            ))
        except Exception:
            reactions.append(_heuristic_reaction(persona, category, price_delta_pct, removed))
    return reactions


def reactions_summary(reactions: list[PersonaReaction]) -> dict:
    total = len(reactions)
    accept = sum(1 for r in reactions if r.reaction == "accept")
    switch = sum(1 for r in reactions if r.reaction == "switch_substitute")
    leave = sum(1 for r in reactions if r.reaction == "leave")
    return {
        "total_personas": total,
        "accept_pct": round(accept / total * 100, 1),
        "switch_pct": round(switch / total * 100, 1),
        "leave_pct": round(leave / total * 100, 1),
        "sample_objections": [r.objection for r in reactions if r.reaction != "accept"][:5],
    }


if __name__ == "__main__":
    reactions = simulate_personas(category="Burgers", price_delta_pct=0.15)
    for r in reactions:
        print(f"[{r.persona_id}] {r.persona_name}: {r.reaction} -- {r.objection}")
    print()
    print(json.dumps(reactions_summary(reactions), indent=2, ensure_ascii=False))

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


# --- promo layer: how guests react to a promotion (not a price change) -------------------------------
PROMO_LABELS = ["Воспользуются акцией", "Присмотрятся", "Не заметят"]


def _heuristic_promo_reaction(persona: dict, channel: str, discount_pct: float) -> PersonaReaction:
    """Без ключа: интерес к акции растёт с чувствительностью к цене и глубиной скидки; в доставке сильнее у delivery-гостей."""
    pull = persona["budget_sensitivity"] * (discount_pct / 30.0)
    if channel != "Ресторан":
        pull *= 1.6 if "Delivery" in persona["name"] else 0.8
    if persona["loyalty"] < 0.35:
        pull *= 1.15   # у нелояльных скидка чаще решает, куда пойти
    name = persona["name"]
    if pull >= 0.45:
        return PersonaReaction(persona["id"], name, "accept", f"{name} заметит акцию и закажет именно по ней", None)
    if pull >= 0.2:
        return PersonaReaction(persona["id"], name, "switch_substitute", f"{name} присмотрится: возьмёт, если акция совпадёт с тем, что хочет", None)
    return PersonaReaction(persona["id"], name, "leave", f"{name} не обратит внимания и закажет как обычно", None)


def simulate_promo_personas(channel: str, discount_pct: float) -> list[PersonaReaction]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return [_heuristic_promo_reaction(p, channel, discount_pct) for p in PERSONAS]
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        return [_heuristic_promo_reaction(p, channel, discount_pct) for p in PERSONAS]
    out = []
    for persona in PERSONAS:
        prompt = f"""You simulate a fast-food guest in Almaty reacting to a promotion.
Persona: {persona['name']}; price sensitivity {persona['budget_sensitivity']} (0-1); loyalty {persona['loyalty']} (0-1); likes: {', '.join(persona['prefers'])}.
Promotion: {discount_pct:.0f}% discount for the guest, channel: {channel}.
Respond ONLY with JSON: {{"reaction": "accept"|"switch_substitute"|"leave", "objection": "<one sentence in Russian, in character>"}}
accept = will use the promo, switch_substitute = will look at it and maybe use, leave = will not notice or care."""
        try:
            msg = client.messages.create(model="claude-sonnet-4-5", max_tokens=200, messages=[{"role": "user", "content": prompt}])
            text = msg.content[0].text.strip()
            data = json.loads(text[text.find("{"):text.rfind("}") + 1])
            out.append(PersonaReaction(persona["id"], persona["name"], data.get("reaction", "switch_substitute"), data.get("objection", ""), None))
        except Exception:
            out.append(_heuristic_promo_reaction(persona, channel, discount_pct))
    return out


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


def promo_reactions_summary(reactions: list[PersonaReaction]) -> dict:
    """Тот же формат, но с подписями для акции (accept=воспользуются, switch=присмотрятся, leave=не заметят)."""
    s = reactions_summary(reactions)
    s["labels"] = PROMO_LABELS
    s["sample_objections"] = [r.objection for r in reactions][:5]
    return s


if __name__ == "__main__":
    reactions = simulate_personas(category="Burgers", price_delta_pct=0.15)
    for r in reactions:
        print(f"[{r.persona_id}] {r.persona_name}: {r.reaction} -- {r.objection}")
    print()
    print(json.dumps(reactions_summary(reactions), indent=2, ensure_ascii=False))
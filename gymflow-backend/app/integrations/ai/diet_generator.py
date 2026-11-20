"""AI diet-plan generation with Claude.

Calorie and macro targets are computed deterministically here (Mifflin-St Jeor);
Claude turns those targets plus the member's preferences and restrictions into
a practical, regionally familiar meal plan returned as validated structured output.
"""
import logging
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

ACTIVITY_FACTOR = 1.55  # moderately active (trains 3-5x / week)
GOAL_ADJUSTMENT = {"weight_loss": -500, "weight_gain": 400, "maintenance": 0}
PROTEIN_G_PER_KG = {"weight_loss": 2.0, "weight_gain": 1.8, "maintenance": 1.6}


class DietGenerationError(RuntimeError):
    pass


# ---- Structured output schema ----

class MealItem(BaseModel):
    food: str
    quantity: str = Field(description="Household measure, e.g. '2 rotis', '1 cup (200 g)'")
    calories: int
    protein_g: float


class Meal(BaseModel):
    name: str = Field(description="e.g. Breakfast, Mid-morning, Lunch, Pre-workout, Dinner")
    time: str = Field(description="24h time, e.g. 08:00")
    items: list[MealItem]


class Macros(BaseModel):
    protein_g: int
    carbs_g: int
    fat_g: int


class DietPlanDraft(BaseModel):
    title: str
    daily_calories: int
    macros: Macros
    meals: list[Meal]
    notes: str = Field(description="Hydration, substitutions and practical tips for the member")


# ---- Inputs and targets ----

@dataclass
class MemberProfile:
    name: str
    gender: str | None
    age: int | None
    height_cm: float
    weight_kg: float
    goal: str            # weight_loss | weight_gain | maintenance
    diet_type: str       # veg | non_veg | eggetarian | vegan
    restrictions: str | None = None
    meals_per_day: int = 5
    cuisine: str = "Indian"
    trainer_notes: str | None = None


def compute_targets(p: MemberProfile) -> tuple[int, Macros]:
    age = p.age or 28
    gender_offset = 5 if p.gender == "male" else -161 if p.gender == "female" else -78
    bmr = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * age + gender_offset
    calories = int(round((bmr * ACTIVITY_FACTOR + GOAL_ADJUSTMENT.get(p.goal, 0)) / 10) * 10)
    calories = max(calories, 1200)
    protein = int(PROTEIN_G_PER_KG.get(p.goal, 1.6) * p.weight_kg)
    fat = int(calories * 0.25 / 9)
    carbs = max(int((calories - protein * 4 - fat * 9) / 4), 50)
    return calories, Macros(protein_g=protein, carbs_g=carbs, fat_g=fat)


SYSTEM_PROMPT = """You are a sports nutritionist working inside a gym management app. \
Trainers review every plan you write before members see it.

Write one day's meal plan that:
- hits the given calorie and macro targets within about 5% (item calories should add up to the daily total)
- strictly respects the diet type and every listed restriction or allergy; never include an excluded food
- uses everyday foods from the stated cuisine that are affordable and easy to find, with household measures
- spreads protein across the day, and places a carb-forward meal before training
Keep notes short and practical: hydration, 2-3 easy substitutions, and anything the trainer should check. \
Do not give medical advice; if the profile suggests a medical condition, say in the notes that a doctor should review the plan."""


def _user_prompt(p: MemberProfile, calories: int, macros: Macros) -> str:
    return (
        f"Member: {p.name}, {p.gender or 'unspecified gender'}, age {p.age or 'unknown'}, "
        f"{p.height_cm:.0f} cm, {p.weight_kg:.1f} kg\n"
        f"Goal: {p.goal.replace('_', ' ')}\n"
        f"Diet type: {p.diet_type}\n"
        f"Restrictions / allergies: {p.restrictions or 'none'}\n"
        f"Cuisine: {p.cuisine}\n"
        f"Meals per day: {p.meals_per_day}\n"
        f"Targets: {calories} kcal, protein {macros.protein_g} g, carbs {macros.carbs_g} g, fat {macros.fat_g} g\n"
        + (f"Trainer notes: {p.trainer_notes}\n" if p.trainer_notes else "")
    )


def is_configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def generate_with_claude(p: MemberProfile) -> DietPlanDraft:
    calories, macros = compute_targets(p)
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = client.beta.messages.parse(
            model=settings.AI_MODEL,
            max_tokens=16000,
            # If a safety classifier declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(p, calories, macros)}],
            output_format=DietPlanDraft,
        )
    except anthropic.RateLimitError as exc:
        raise DietGenerationError("AI service is busy, please try again in a minute") from exc
    except anthropic.APIStatusError as exc:
        logger.error("Claude API error %s: %s", exc.status_code, exc.message)
        raise DietGenerationError("AI service returned an error") from exc
    except anthropic.APIConnectionError as exc:
        raise DietGenerationError("Could not reach the AI service") from exc

    if response.stop_reason == "refusal":
        raise DietGenerationError("The AI declined to generate this plan; please create it manually")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise DietGenerationError("The AI response was incomplete; please try again")
    return response.parsed_output


# ---- Offline fallback (no API key configured) ----

_TEMPLATE_FOODS = {
    "veg": [("Paneer bhurji", "100 g", 265, 18), ("Moong dal chilla", "2 pieces", 240, 14),
            ("Rajma", "1 cup", 230, 15), ("Curd", "1 cup", 100, 8)],
    "vegan": [("Tofu stir-fry", "150 g", 220, 20), ("Moong dal chilla", "2 pieces", 240, 14),
              ("Chana masala", "1 cup", 270, 14), ("Soy milk", "1 glass", 100, 7)],
    "eggetarian": [("Egg omelette", "3 eggs", 230, 18), ("Paneer tikka", "100 g", 265, 18),
                   ("Dal", "1 cup", 200, 12), ("Curd", "1 cup", 100, 8)],
    "non_veg": [("Egg omelette", "3 eggs", 230, 18), ("Grilled chicken", "150 g", 250, 45),
                ("Fish curry", "150 g", 230, 30), ("Curd", "1 cup", 100, 8)],
}


def generate_from_template(p: MemberProfile) -> DietPlanDraft:
    calories, macros = compute_targets(p)
    foods = _TEMPLATE_FOODS.get(p.diet_type, _TEMPLATE_FOODS["veg"])
    slots = [("Breakfast", "08:00", 0.25), ("Mid-morning", "11:00", 0.10), ("Lunch", "13:30", 0.30),
             ("Pre-workout", "17:00", 0.10), ("Dinner", "20:30", 0.25)]
    meals = []
    for i, (name, time, share) in enumerate(slots):
        food, qty, kcal, protein = foods[i % len(foods)]
        carb_kcal = max(int(calories * share) - kcal, 0)
        items = [MealItem(food=food, quantity=qty, calories=kcal, protein_g=protein)]
        if carb_kcal:
            items.append(MealItem(food="Rice / roti / oats (adjust portion)", quantity=f"~{carb_kcal} kcal",
                                  calories=carb_kcal, protein_g=round(carb_kcal * 0.03, 1)))
        meals.append(Meal(name=name, time=time, items=items))
    return DietPlanDraft(
        title=f"{p.goal.replace('_', ' ').title()} plan for {p.name}",
        daily_calories=calories, macros=macros, meals=meals,
        notes="Template plan (AI not configured). Drink 3-4 L of water daily. Trainer: review portions.",
    )


def generate_diet_plan(p: MemberProfile) -> tuple[DietPlanDraft, bool]:
    """Returns (plan, ai_generated)."""
    if is_configured():
        return generate_with_claude(p), True
    return generate_from_template(p), False

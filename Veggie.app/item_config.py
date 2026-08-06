"""
item_config.py
---------------
Single source of truth for:
  1. ITEMS        -> every item the store carries, its order category
                      (basic / other / fruit) and its counting unit
                      (kg = by weight, box = by box/bunch count).
  2. ORDER_CALENDAR -> which days we place a "full" order, a "basic"
                        order, or no order at all.
  3. Helper functions that work out, for any order day, which items
     are on that order and how many days that order has to cover
     before the next delivery of that same category arrives.

Business rules encoded here (as given by the store manager):

  Basic order items:
    bindi/okra, green chilli, coriander, mint, lauki, drumstick,
    tindoora, arbi, small onion, amla, brinjal purple, brinjal green,
    gwar, karela, paneer, papdi

  Full order = Basic items + "Other" veggies + Fruits:
    Other  -> methi, turia/toria, parwal, ash gourd, vallerika,
              puja coconut, ginger, garlic, green banana, green mango,
              matoki, pan leaves, suran, long beans
    Fruits -> guava, chikoo, custard apple, alphonso mango, kesar mango,
              banganpally mango

  Weekly order calendar:
    Monday    -> Full order
    Tuesday   -> No order
    Wednesday -> Basic order
    Thursday  -> Basic order
    Friday    -> Full order
    Saturday  -> Basic order
    Sunday    -> No order  (store's original list didn't mention Sunday;
                            assumed closed for ordering like Tuesday -
                            change ORDER_CALENDAR below if that's wrong)

  Units:
    Coriander and Mint are counted in BOXES (bunches/sticks per box),
    e.g. 10 stk, 20 stk. Every other item is counted by WEIGHT (kg).

NOTE ON TASK 1 vs TASK 2:
  Task 2 was described as "the same as Task 1, in more detail" and gives
  a longer, more specific item list. This file therefore implements
  Task 2's item list as the live/canonical one (it's a superset of
  Task 1's shorter basic list: bindi, okra, chilli, coriander, mint,
  lauki, drumstick). If you actually need the two task item-lists to
  behave differently (e.g. two different stores), duplicate this file
  and swap the ITEMS dict.
"""

from __future__ import annotations

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# category: "basic" | "other" | "fruit"
#   - "basic"  -> ordered on Basic order days AND Full order days
#   - "other"/"fruit" -> ordered ONLY on Full order days
# unit: "kg" (by weight) or "box" (by box/bunch count)
ITEMS: dict[str, dict] = {
    # ---------------- Basic order items ----------------
    "Bindi Okra":       {"category": "basic", "unit": "kg"},
    "Green Chilli":     {"category": "basic", "unit": "kg"},
    "Coriander":        {"category": "basic", "unit": "box"},
    "Mint":             {"category": "basic", "unit": "box"},
    "Lauki":            {"category": "basic", "unit": "kg"},
    "Drum Sticks":      {"category": "basic", "unit": "kg"},
    "Tindoora":         {"category": "basic", "unit": "kg"},
    "Arbi":             {"category": "basic", "unit": "kg"},
    "Small Onion":      {"category": "basic", "unit": "kg"},
    "Amla":             {"category": "basic", "unit": "kg"},
    "Brinjal Purple":   {"category": "basic", "unit": "kg"},
    "Brinjal Green":    {"category": "basic", "unit": "kg"},
    "Gwar":             {"category": "basic", "unit": "kg"},
    "Karela":           {"category": "basic", "unit": "kg"},
    "Paneer":           {"category": "basic", "unit": "kg"},
    "Papdi":            {"category": "basic", "unit": "kg"},

    # ---------------- Other veggies (Full order only) ----------------
    "Methi Leaves":     {"category": "other", "unit": "kg"},
    "Toria":            {"category": "other", "unit": "kg"},   # Turia
    "Parwal":           {"category": "other", "unit": "kg"},
    "Ashgourd":         {"category": "other", "unit": "kg"},   # Ash gourd
    "Vellarikai":       {"category": "other", "unit": "kg"},   # Vallerika
    "Puja Coconut":     {"category": "other", "unit": "kg"},
    "Ginger":           {"category": "other", "unit": "kg"},
    "Garlic":           {"category": "other", "unit": "kg"},
    "Green Banana":     {"category": "other", "unit": "kg"},
    "Green Mango":      {"category": "other", "unit": "kg"},
    "Matoki":           {"category": "other", "unit": "kg"},
    "Pan Leaves":       {"category": "other", "unit": "kg"},
    "Suran":            {"category": "other", "unit": "kg"},
    "Long Beans":       {"category": "other", "unit": "kg"},

    # ---------------- Fruits (Full order only) ----------------
    "Guava":              {"category": "fruit", "unit": "kg"},
    "Chikoo":             {"category": "fruit", "unit": "kg"},
    "Custard Apple":      {"category": "fruit", "unit": "kg"},
    "Alphonso Mango":     {"category": "fruit", "unit": "kg"},
    "Kesar Mango":        {"category": "fruit", "unit": "kg"},
    "Banganpally Mango":  {"category": "fruit", "unit": "kg"},
}

# Weekday -> order rule. order_type is "full", "basic", or None (no order).
ORDER_CALENDAR: dict[str, dict | None] = {
    "Monday":    {"order_type": "full"},
    "Tuesday":   None,
    "Wednesday": {"order_type": "basic"},
    "Thursday":  {"order_type": "basic"},
    "Friday":    {"order_type": "full"},
    "Saturday":  {"order_type": "basic"},
    "Sunday":    None,
}


def order_type_for_day(day: str) -> str | None:
    """'full' | 'basic' | None for a given weekday name."""
    rule = ORDER_CALENDAR.get(day)
    return rule["order_type"] if rule else None


def items_for_order_day(order_day: str) -> dict[str, dict]:
    """Which items (name -> meta) are actually ordered on this weekday."""
    order_type = order_type_for_day(order_day)
    if order_type is None:
        return {}
    if order_type == "full":
        return dict(ITEMS)
    # basic order day -> basic-category items only
    return {name: meta for name, meta in ITEMS.items() if meta["category"] == "basic"}


def _category_eligible_on(day: str, category: str) -> bool:
    order_type = order_type_for_day(day)
    if order_type is None:
        return False
    if order_type == "full":
        return True
    return order_type == "basic" and category == "basic"


def coverage_weekdays(order_day: str, category: str) -> list[str]:
    """
    The list of weekdays (starting with order_day) that an order placed
    on order_day for an item of this category needs to cover, i.e. every
    day up to (but not including) the next day this category gets
    reordered.

    Example with the calendar above:
      coverage_weekdays("Monday", "basic")  -> ["Monday", "Tuesday"]
      coverage_weekdays("Monday", "other")  -> ["Monday","Tuesday","Wednesday","Thursday"]
      coverage_weekdays("Friday", "basic")  -> ["Friday"]
      coverage_weekdays("Friday", "other")  -> ["Friday","Saturday","Sunday"]
    """
    if order_day not in WEEKDAYS:
        raise ValueError(f"Unknown weekday: {order_day}")

    idx = WEEKDAYS.index(order_day)
    days = [WEEKDAYS[idx]]
    i = idx
    for _ in range(6):
        i = (i + 1) % 7
        day = WEEKDAYS[i]
        if _category_eligible_on(day, category):
            break
        days.append(day)
    return days


def order_days_available() -> list[str]:
    """Weekdays (in week order) that actually have an order placed."""
    return [d for d in WEEKDAYS if ORDER_CALENDAR.get(d) is not None]

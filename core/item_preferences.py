"""
core/item_preferences.py
Items given to the bot affect personality traits.
Each item has a preference value that modifies curiosity, affection, aggression, boredom.
"""

# Item preference mapping
# Format: item_name -> {"affection": +/-value, "boredom": +/-value, "curiosity": +/-value, "aggression": +/-value}
ITEM_PREFERENCES = {
    # FOOD - increases affection, decreases boredom
    "fish": {"affection": +15, "boredom": -20, "description": "nom nom! fish is my fave!"},
    "raw_salmon": {"affection": +10, "boredom": -15},
    "raw_cod": {"affection": +10, "boredom": -15},
    "salmon": {"affection": +12, "boredom": -18},
    "cod": {"affection": +12, "boredom": -18},
    "tropical_fish": {"affection": +20, "boredom": -25, "description": "ooh fancy fish!!"},
    "pufferfish": {"affection": +5, "boredom": -5, "description": "spiky little guy"},

    # PLUSHIES - very high affection boost
    "blahaj:blue_shark": {"affection": +25, "boredom": -10, "description": "*bounces excitedly* SHARK PLUSH!!!"},
    "shark_plush": {"affection": +25, "boredom": -10},
    "cat_plush": {"affection": +20, "boredom": -5, "description": "*purrs* fellow feline!!"},
    "plush": {"affection": +15, "boredom": -8},

    # TREASURES - curiosity increases
    "diamond": {"curiosity": +20, "affection": +5, "description": "sparkly!"},
    "emerald": {"curiosity": +15, "affection": +5},
    "amethyst_shard": {"curiosity": +10, "affection": +3},
    "gold_block": {"curiosity": +10, "affection": +8},

    # TOYS - aggression & energy
    "stick": {"aggression": +10, "boredom": -5, "description": "ooh a stick! wanna play??"},
    "string": {"aggression": +8, "boredom": -5},

    # SPECIAL - big reactions
    "enchanted_golden_apple": {"affection": +30, "curiosity": +20, "description": "WHOA that's fancy!!"},
    "dragon_egg": {"curiosity": +40, "aggression": +10, "description": "the DRAGON EGG?! legendary!!"},
    "nether_star": {"curiosity": +35, "affection": +15, "description": "a NETHER STAR!! you're amazing!"},

    # DEFAULT - modest boost for unknown items
    "default": {"affection": +3, "curiosity": +2}
}


class ItemPreferences:
    """Manages trait changes based on items given to the bot."""

    def __init__(self):
        self.last_held_item = None
        self.item_history = []  # Track items given for memory

    def get_preference(self, item_name: str) -> dict:
        """Get trait changes for an item."""
        if not item_name:
            return {}

        # Normalize item name: lowercase, remove minecraft: prefix
        normalized = item_name.lower().replace("minecraft:", "")

        # Exact match
        if normalized in ITEM_PREFERENCES:
            return ITEM_PREFERENCES[normalized].copy()

        # Partial matches
        for key, prefs in ITEM_PREFERENCES.items():
            if key in normalized or normalized in key:
                return prefs.copy()

        # Default for unknown items
        return ITEM_PREFERENCES["default"].copy()

    def apply_item_to_traits(self, item_name: str, traits: object) -> dict:
        """
        Apply item preferences to trait object.
        Returns dict of what changed for logging.
        """
        prefs = self.get_preference(item_name)
        if not prefs:
            return {}

        changes = {}

        # Apply each trait modifier
        for trait_name, delta in prefs.items():
            if trait_name in ("affection", "curiosity", "aggression", "boredom", "description"):
                if trait_name != "description" and hasattr(traits, trait_name):
                    old_val = getattr(traits, trait_name, 50.0)
                    new_val = max(0.0, min(100.0, old_val + delta))
                    setattr(traits, trait_name, new_val)
                    changes[trait_name] = {"old": old_val, "new": new_val, "delta": delta}

        return changes

    def get_reaction_message(self, item_name: str) -> str:
        """Get custom reaction message for an item."""
        prefs = self.get_preference(item_name)
        if "description" in prefs:
            return prefs["description"]

        # Generate generic reaction based on trait changes
        affection_delta = prefs.get("affection", 0)
        boredom_delta = prefs.get("boredom", 0)
        curiosity_delta = prefs.get("curiosity", 0)

        if affection_delta > 15:
            return "*purrs loudly* you're so sweet to me!"
        elif affection_delta > 5:
            return "*happy tail swish* thank you!"
        elif curiosity_delta > 15:
            return "ooh where did you GET this??"
        elif boredom_delta < -15:
            return "*perks up* oh hey, something new!"
        else:
            return "neat, thanks!"
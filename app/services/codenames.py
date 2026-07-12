import random

ADJECTIVES = [
    "Jolly", "Merry", "Cozy", "Twinkly", "Frosty", "Sparkly", "Cheerful",
    "Snowy", "Sunny", "Gentle", "Bright", "Golden", "Silver", "Peppy",
    "Bubbly", "Dandy", "Plucky", "Rosy", "Toasty", "Whimsical",
]
ANIMALS = [
    "Penguin", "Reindeer", "Polar Bear", "Fox", "Owl", "Bunny", "Otter",
    "Hedgehog", "Robin", "Cardinal", "Puppy", "Kitten", "Panda", "Koala",
    "Dolphin", "Seal", "Chipmunk", "Squirrel", "Lamb", "Duckling",
]


def generate_codenames(n: int):
    """n unique friendly codenames like 'Jolly Penguin'."""
    combos = [f"{a} {b}" for a in ADJECTIVES for b in ANIMALS]
    random.shuffle(combos)
    if n > len(combos):
        combos += [f"{c} {i}" for i, c in enumerate(combos, 2)]
    return combos[:n]

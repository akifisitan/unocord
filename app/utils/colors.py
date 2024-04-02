from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Colors:
    Red = 0xFC4A4A
    Rose = 0xFE5A8D
    Orange = 0xF75829
    Emerald = 0x1BBD9C
    ColorList = [
        Red,
        Rose,
        Orange,
        Emerald,
    ]


def random_color() -> int:
    return random.choice(Colors.ColorList)

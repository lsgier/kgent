import math
from collections import Counter

from models import Person

def compute_name_idf(persons: list[Person]) -> dict[str, float]:
    freq = Counter(p.name for p in persons)
    n = len(persons)
    idf = {name: math.log(n / count) for name, count in freq.items()}

    idf_min, idf_max = min(idf.values()), max(idf.values())
    span = idf_max - idf_min
    if span == 0:
        return {name: 1.0 for name in idf}
    return {name: (value - idf_min) / span for name, value in idf.items()}
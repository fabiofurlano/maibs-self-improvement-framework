# Pipeline Solve — 2026-06-10 23:34

**Task:** Write a function to choose specified number of colours from three different colours and generate all the combinations with repetitions.

**Path taken:** attempt_1_pass

**Solution:**
```python
from itertools import combinations_with_replacement

def combinations_colors(colors, n):
    return list(combinations_with_replacement(colors, n))
```

**Attempts:** 1

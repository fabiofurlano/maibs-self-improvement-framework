# Pipeline Solve — 2026-06-10 23:34

**Task:** Write a function to compute binomial probability for the given number.

**Path taken:** attempt_1_pass

**Solution:**
```python
import math

def binomial_probability(n, k, p):
    """
    Compute the binomial probability P(X = k) for n trials,
    k successes, and success probability p.
    """
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))
```

**Attempts:** 1

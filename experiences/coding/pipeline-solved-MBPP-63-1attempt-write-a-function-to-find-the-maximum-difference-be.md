# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function to find the maximum difference between available pairs in the given tuple list.

**Path taken:** attempt_1_pass

**Solution:**
```python
def max_difference(pairs):
    return max(abs(a - b) for a, b in pairs)
```

**Attempts:** 1

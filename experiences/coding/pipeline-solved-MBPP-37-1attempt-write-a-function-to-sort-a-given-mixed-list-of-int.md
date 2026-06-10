# Pipeline Solve — 2026-06-10 23:41

**Task:** Write a function to sort a given mixed list of integers and strings.

**Path taken:** attempt_1_pass

**Solution:**
```python
def sort_mixed_list(mixed_list):
    numbers = sorted([x for x in mixed_list if isinstance(x, int)])
    strings = sorted([x for x in mixed_list if isinstance(x, str)])
    return numbers + strings
```

**Attempts:** 1

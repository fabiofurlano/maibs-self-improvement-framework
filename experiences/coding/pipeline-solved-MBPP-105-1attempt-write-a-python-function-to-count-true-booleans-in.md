# Pipeline Solve — 2026-06-10 23:41

**Task:** Write a python function to count true booleans in the given list.

**Path taken:** attempt_1_pass

**Solution:**
```python
def count(lst):
    return sum(1 for item in lst if item is True)
```

**Attempts:** 1

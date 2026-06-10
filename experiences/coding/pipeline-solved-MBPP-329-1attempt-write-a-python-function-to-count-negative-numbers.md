# Pipeline Solve — 2026-06-10 23:56

**Task:** Write a python function to count negative numbers in a list.

**Path taken:** attempt_1_pass

**Solution:**
```python
def neg_count(lst):
    return sum(1 for num in lst if num < 0)
```

**Attempts:** 1

# Pipeline Solve — 2026-06-10 23:47

**Task:** Write a function to find the minimum value in a given heterogeneous list.

**Path taken:** attempt_1_pass

**Solution:**
```python
def min_val(lst):
    # Filter the list to keep only numeric values (int and float)
    numbers = [item for item in lst if isinstance(item, (int, float))]
    # Return the minimum of the numeric values
    return min(numbers)
```

**Attempts:** 1

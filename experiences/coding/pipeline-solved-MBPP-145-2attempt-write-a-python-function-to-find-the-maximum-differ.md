# Pipeline Solve — 2026-06-10 23:57

**Task:** Write a python function to find the maximum difference between any two elements in a given array.

**Path taken:** attempt_2_pass

**Solution:**
```python
def max_Abs_Diff(arr, n):
    max_val = max(arr)
    min_val = min(arr)
    return abs(max_val - min_val)

# Test with the example
print(max_Abs_Diff((2, 1, 5, 3), 4))  # Output: 4
```

**Attempts:** 2

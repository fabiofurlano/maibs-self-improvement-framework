# Pipeline Solve — 2026-06-10 23:55

**Task:** Write a function to check if the common elements between two given lists are in the same order or not.

**Path taken:** attempt_1_pass

**Solution:**
```python
def same_order(a, b):
    # Filter both lists to keep only common elements, preserving their original order
    a_filtered = [x for x in a if x in b]
    b_filtered = [x for x in b if x in a]
    # The common elements appear in the same order if and only if the filtered lists are equal
    return a_filtered == b_filtered
```

**Attempts:** 1

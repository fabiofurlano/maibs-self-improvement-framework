# Pipeline Solve — 2026-06-10 23:57

**Task:** Write a function to search an element in the given array by using sequential search.

**Path taken:** attempt_1_pass

**Solution:**
```python
def sequential_search(arr, target):
    for i in range(len(arr)):
        if arr[i] == target:
            return (True, i)
    return (False, -1)
```

**Attempts:** 1

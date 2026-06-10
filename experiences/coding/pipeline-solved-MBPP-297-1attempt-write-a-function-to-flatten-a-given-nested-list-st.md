# Pipeline Solve — 2026-06-10 23:56

**Task:** Write a function to flatten a given nested list structure.

**Path taken:** attempt_1_pass

**Solution:**
```python
def flatten_list(nested_list):
    result = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)
    return result
```

**Attempts:** 1

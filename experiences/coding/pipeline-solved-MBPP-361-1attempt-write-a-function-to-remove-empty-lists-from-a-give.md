# Pipeline Solve — 2026-06-10 23:46

**Task:** Write a function to remove empty lists from a given list of lists.

**Path taken:** attempt_1_pass

**Solution:**
```python
def remove_empty(input_list):
    return [item for item in input_list if not (isinstance(item, list) and len(item) == 0)]
```

**Attempts:** 1

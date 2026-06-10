# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function to split a list for every nth element.

**Path taken:** attempt_1_pass

**Solution:**
```python
def list_split(input_list, n):
    return [input_list[i::n] for i in range(n)]
```

**Attempts:** 1

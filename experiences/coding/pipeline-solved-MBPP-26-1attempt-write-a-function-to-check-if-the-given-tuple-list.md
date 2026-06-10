# Pipeline Solve — 2026-06-10 23:33

**Task:** Write a function to check if the given tuple list has all k elements.

**Path taken:** attempt_1_pass

**Solution:**
```python
def check_k_elements(tuple_list, k):
    return all(element == k for tup in tuple_list for element in tup)
```

**Attempts:** 1

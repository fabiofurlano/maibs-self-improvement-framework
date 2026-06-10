# Pipeline Solve — 2026-06-10 23:57

**Task:** Write a function to sort a list of tuples in increasing order by the last element in each tuple.

**Path taken:** attempt_1_pass

**Solution:**
```python
def sort_tuple(tuples):
    return sorted(tuples, key=lambda x: x[-1])
```

**Attempts:** 1

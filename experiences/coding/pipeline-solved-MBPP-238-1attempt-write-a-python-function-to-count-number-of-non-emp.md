# Pipeline Solve — 2026-06-10 23:45

**Task:** Write a python function to count number of non-empty substrings of a given string.

**Path taken:** attempt_1_pass

**Solution:**
```python
def number_of_substrings(s):
    n = len(s)
    return n * (n + 1) // 2
```

**Attempts:** 1

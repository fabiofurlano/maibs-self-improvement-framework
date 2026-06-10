# Pipeline Solve — 2026-06-10 23:48

**Task:** Write a function to check if a string represents an integer or not.

**Path taken:** attempt_1_pass

**Solution:**
```python
def check_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False
```

**Attempts:** 1

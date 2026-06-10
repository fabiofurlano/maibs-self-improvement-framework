# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function to calculate the number of digits and letters in a string.

**Path taken:** attempt_1_pass

**Solution:**
```python
def dig_let(s):
    letters = sum(1 for c in s if c.isalpha())
    digits = sum(1 for c in s if c.isdigit())
    return (letters, digits)
```

**Attempts:** 1

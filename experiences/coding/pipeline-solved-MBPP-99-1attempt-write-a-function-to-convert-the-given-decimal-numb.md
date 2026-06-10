# Pipeline Solve — 2026-06-10 23:55

**Task:** Write a function to convert the given decimal number to its binary equivalent.

**Path taken:** attempt_1_pass

**Solution:**
```python
def decimal_to_binary(decimal_number):
    if decimal_number == 0:
        return '0'
    binary_digits = []
    while decimal_number > 0:
        binary_digits.append(str(decimal_number % 2))
        decimal_number //= 2
    return ''.join(reversed(binary_digits))
```

**Attempts:** 1

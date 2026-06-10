# Pipeline Solve — 2026-06-10 23:37

**Task:** Write a python function to find number of integers with odd number of set bits.

**Path taken:** attempt_2_pass

**Solution:**
```python
def count_With_Odd_SetBits(n):
    count = 0
    for i in range(n + 1):
        if bin(i).count('1') % 2 == 1:
            count += 1
    return count
```

**Attempts:** 2

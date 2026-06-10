# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a python function to find the sum of squares of first n odd natural numbers.

**Path taken:** attempt_1_pass

**Solution:**
```python
def square_Sum(n):
    return sum((2*i - 1)**2 for i in range(1, n + 1))
```

**Attempts:** 1

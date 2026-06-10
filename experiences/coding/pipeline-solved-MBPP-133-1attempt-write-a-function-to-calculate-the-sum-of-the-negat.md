# Pipeline Solve — 2026-06-10 23:57

**Task:** Write a function to calculate the sum of the negative numbers of a given list of numbers using lambda function.

**Path taken:** attempt_1_pass

**Solution:**
```python
def sum_negativenum(nums):
    return sum(filter(lambda x: x < 0, nums))
```

**Attempts:** 1

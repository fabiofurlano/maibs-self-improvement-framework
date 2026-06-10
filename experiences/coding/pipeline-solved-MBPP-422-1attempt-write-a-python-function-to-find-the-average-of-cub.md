# Pipeline Solve — 2026-06-10 23:40

**Task:** Write a python function to find the average of cubes of first n natural numbers.

**Path taken:** attempt_1_pass

**Solution:**
```python
def find_Average_Of_Cube(n):
    """
    Find the average of cubes of first n natural numbers.
    
    Using the formula: Sum of cubes = [n(n+1)/2]^2
    Therefore, Average = [n(n+1)/2]^2 / n = n(n+1)^2 / 4
    
    Args:
        n: Number of natural numbers
        
    Returns:
        Average of cubes of first n natural numbers
    """
    if n <= 0:
        return 0
    return n * (n + 1) ** 2 / 4
```

**Attempts:** 1

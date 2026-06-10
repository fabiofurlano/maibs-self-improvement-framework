# Pipeline Solve — 2026-06-10 23:35

**Task:** Write a python function to find the largest prime factor of a given number.

**Path taken:** attempt_2_pass

**Solution:**
```python
def max_Prime_Factors(n):
    # Handle edge case
    if n <= 1:
        return None
    
    # Initialize the largest prime factor
    largest = 1
    
    # Check for factor 2 (the only even prime)
    while n % 2 == 0:
        largest = 2
        n = n // 2
    
    # Check for odd factors from 3 up to sqrt(n)
    i = 3
    while i * i <= n:
        while n % i == 0:
            largest = i
            n = n // i
        i += 2
    
    # If n is still greater than 1, it is a prime factor itself
    if n > 1:
        largest = n
    
    return largest
```

**Attempts:** 2

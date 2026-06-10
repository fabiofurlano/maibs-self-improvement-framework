# Pipeline Solve — 2026-06-10 23:56

**Task:** Write a python function to find binomial co-efficient.

**Path taken:** attempt_1_pass

**Solution:**
```python
def binomial_Coeff(n, k):
    """
    Calculate the binomial coefficient C(n, k) = n! / (k! * (n-k)!)
    
    Parameters:
        n (int): Total number of items
        k (int): Number of items to choose
    
    Returns:
        int: The binomial coefficient C(n, k)
    """
    # Handle edge cases
    if k < 0 or k > n:
        return 0
    if k == 0 or k == n:
        return 1
    
    # Use symmetry: C(n, k) == C(n, n-k) to minimize iterations
    k = min(k, n - k)
    
    # Compute iteratively to keep intermediate values small
    # C(n, k) = (n * (n-1) * ... * (n-k+1)) / (k!)
    result = 1
    for i in range(k):
        result = result * (n - i) // (i + 1)
    
    return result
```

**Attempts:** 1

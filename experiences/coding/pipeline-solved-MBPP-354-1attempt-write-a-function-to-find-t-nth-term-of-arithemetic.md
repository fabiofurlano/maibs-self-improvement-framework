# Pipeline Solve — 2026-06-10 23:40

**Task:** Write a function to find t-nth term of arithemetic progression.

**Path taken:** attempt_1_pass

**Solution:**
```python
def tn_ap(a, n, d):
    """
    Find the nth term of an arithmetic progression.
    
    Parameters:
    a (int/float): The first term of the arithmetic progression.
    n (int): The term number to find (1-indexed).
    d (int/float): The common difference between consecutive terms.
    
    Returns:
    int/float: The nth term of the arithmetic progression.
    """
    return a + (n - 1) * d
```

**Attempts:** 1

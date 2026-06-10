# Pipeline Solve — 2026-06-10 23:33

**Task:** Write a python function to find the sum of squares of first n even natural numbers.

**Path taken:** attempt_1_pass

**Solution:**
```python
def square_Sum(n):
    """
    Calculate the sum of squares of the first n even natural numbers.
    
    Args:
        n (int): The number of even natural numbers to consider.
    
    Returns:
        int: The sum of squares of the first n even natural numbers.
    """
    # Using formula: sum of (2i)^2 for i=1 to n = 4 * sum(i^2) for i=1 to n
    #              = 4 * n(n+1)(2n+1)/6 = 2n(n+1)(2n+1)/3
    return 2 * n * (n + 1) * (2 * n + 1) // 3


# Alternative implementation using a loop
def square_Sum_loop(n):
    total = 0
    for i in range(1, n + 1):
        total += (2 * i) ** 2
    return total


# Test cases
if __name__ == "__main__":
    print(square_Sum(2))      # Expected: 20
    print(square_Sum(3))      # Expected: 4 + 16 + 36 = 56
    print(square_Sum(4))      # Expected: 4 + 16 + 36 + 64 = 120
    print(square_Sum(1))      # Expected: 4
    print(square_Sum(5))      # Expected: 4 + 16 + 36 + 64 + 100 = 220
    
    # Verify with loop version
    for i in range(1, 6):
        assert square_Sum(i) == square_Sum_loop(i), f"Mismatch at n={i}"
    print("All tests passed!")
```

**Attempts:** 1

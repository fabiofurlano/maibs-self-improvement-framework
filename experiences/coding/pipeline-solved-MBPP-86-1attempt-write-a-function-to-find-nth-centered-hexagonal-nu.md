# Pipeline Solve — 2026-06-10 23:45

**Task:** Write a function to find nth centered hexagonal number.

**Path taken:** attempt_1_pass

**Solution:**
```python
def centered_hexagonal_number(n):
    """
    Return the nth centered hexagonal number.
    
    The formula for the nth centered hexagonal number is: 3n(n-1) + 1
    
    Parameters:
    n (int): The position in the centered hexagonal number sequence (n >= 1)
    
    Returns:
    int: The nth centered hexagonal number
    """
    return 3 * n * (n - 1) + 1


# Example usage and verification
if __name__ == "__main__":
    # Test cases
    print(centered_hexagonal_number(1))   # 1
    print(centered_hexagonal_number(2))   # 7
    print(centered_hexagonal_number(3))   # 19
    print(centered_hexagonal_number(4))   # 37
    print(centered_hexagonal_number(10))  # 271
```

**Attempts:** 1

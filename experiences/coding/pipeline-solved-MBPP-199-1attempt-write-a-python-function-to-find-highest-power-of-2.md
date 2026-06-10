# Pipeline Solve — 2026-06-10 23:35

**Task:** Write a python function to find highest power of 2 less than or equal to given number.

**Path taken:** attempt_1_pass

**Solution:**
```python
def highest_Power_of_2(n):
    """
    Find the highest power of 2 that is less than or equal to n.
    
    Args:
        n (int): A non-negative integer.
    
    Returns:
        int: The highest power of 2 <= n. Returns 0 if n < 1.
    """
    if n < 1:
        return 0
    # bit_length gives the number of bits needed to represent n.
    # 1 << (bit_length - 1) gives the highest power of 2 <= n.
    return 1 << (n.bit_length() - 1)


# Examples
if __name__ == "__main__":
    print(highest_Power_of_2(10))   # 8
    print(highest_Power_of_2(16))   # 16
    print(highest_Power_of_2(1))    # 1
    print(highest_Power_of_2(2))    # 2
    print(highest_Power_of_2(100))  # 64
    print(highest_Power_of_2(0))    # 0
    print(highest_Power_of_2(1024)) # 1024
```

**Attempts:** 1

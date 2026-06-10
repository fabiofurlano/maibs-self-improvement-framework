# Pipeline Solve — 2026-06-10 23:35

**Task:** Write a python function to convert octal number to decimal number.

**Path taken:** attempt_1_pass

**Solution:**
```python
def octal_To_Decimal(n):
    """
    Convert an octal number to a decimal number.
    
    Parameters:
        n (int or str): The octal number to convert.
    
    Returns:
        int: The decimal equivalent of the octal number.
    
    Example:
        >>> octal_To_Decimal(25)
        21
    """
    # Convert input to string to handle both int and str inputs
    octal_str = str(n)
    
    decimal = 0
    power = 0
    
    # Process each digit from right (least significant) to left
    for digit in reversed(octal_str):
        if not digit.isdigit() or int(digit) >= 8:
            raise ValueError(f"Invalid octal digit '{digit}' in input '{n}'")
        decimal += int(digit) * (8 ** power)
        power += 1
    
    return decimal


# Example usage
if __name__ == "__main__":
    print(octal_To_Decimal(25))    # Output: 21
    print(octal_To_Decimal(17))    # Output: 15
    print(octal_To_Decimal(123))   # Output: 83
    print(octal_To_Decimal("777")) # Output: 511
```

**Attempts:** 1

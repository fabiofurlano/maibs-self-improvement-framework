# Pipeline Solve — 2026-06-10 23:56

**Task:** Write a python function to find the volume of a triangular prism.

**Path taken:** attempt_1_pass

**Solution:**
```python
def find_Volume(a, b, l):
    """
    Calculate the volume of a triangular prism.
    
    Parameters:
    a (float): base of the triangular cross-section
    b (float): height of the triangular cross-section
    l (float): length of the prism
    
    Returns:
    float: volume of the triangular prism
    """
    return (1/2) * a * b * l

# Example usage
print(find_Volume(10, 8, 6))  # Output: 240.0
```

**Attempts:** 1

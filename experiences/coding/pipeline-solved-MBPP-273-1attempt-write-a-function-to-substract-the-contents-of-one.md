# Pipeline Solve — 2026-06-10 23:56

**Task:** Write a function to substract the contents of one tuple with corresponding index of other tuple.

**Path taken:** attempt_1_pass

**Solution:**
```python
def substract_elements(tuple1, tuple2):
    """Substract corresponding elements of two tuples.
    
    Args:
        tuple1: First tuple (minuend).
        tuple2: Second tuple (subtrahend).
    
    Returns:
        A new tuple with the element-wise subtraction (tuple1[i] - tuple2[i]).
    """
    if len(tuple1) != len(tuple2):
        raise ValueError("Tuples must have the same length")
    return tuple(a - b for a, b in zip(tuple1, tuple2))
```

**Attempts:** 1

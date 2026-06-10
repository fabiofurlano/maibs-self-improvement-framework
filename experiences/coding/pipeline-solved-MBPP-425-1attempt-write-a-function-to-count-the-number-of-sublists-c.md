# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function to count the number of sublists containing a particular element.

**Path taken:** attempt_1_pass

**Solution:**
```python
def count_element_in_list(lst, element):
    """
    Counts the number of sublists that contain the given element.
    
    Args:
        lst: A list of sublists (iterables) to search through.
        element: The element to look for in each sublist.
    
    Returns:
        The number of sublists that contain the element.
    """
    count = 0
    for sublist in lst:
        if element in sublist:
            count += 1
    return count
```

**Attempts:** 1

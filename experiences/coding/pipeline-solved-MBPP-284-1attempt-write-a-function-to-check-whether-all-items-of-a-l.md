# Pipeline Solve — 2026-06-10 23:34

**Task:** Write a function to check whether all items of a list are equal to a given string.

**Path taken:** attempt_1_pass

**Solution:**
```python
def check_element(list1, str1):
    """
    Check whether all items in a list are equal to a given string.
    
    Args:
        list1: The list to check.
        str1: The string to compare each item against.
    
    Returns:
        True if all items in the list are equal to str1, False otherwise.
        Returns True for an empty list (vacuous truth).
    """
    return all(item == str1 for item in list1)
```

**Attempts:** 1

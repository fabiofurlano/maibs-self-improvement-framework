# Pipeline Solve — 2026-06-10 21:33

**Task:** Write a function that sorts a list of tuples by the second element

**Path taken:** experience_index → attempt_1_fail → attempt_2_fail → attempt_3_pass_reasoning

**Solution:**
```python
def sort_by_second(list_of_tuples):
    """
    Sort a list of tuples based on the second element of each tuple.

    Args:
        list_of_tuples (list): A list where each element is a tuple.

    Returns:
        list: A new list containing the tuples sorted by their second element.
    """
    return sorted(list_of_tuples, key=lambda item: item[1])
```

**Attempts:** 3

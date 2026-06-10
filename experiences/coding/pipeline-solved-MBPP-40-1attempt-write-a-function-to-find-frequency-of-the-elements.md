# Pipeline Solve — 2026-06-10 23:37

**Task:** Write a function to find frequency of the elements in a given list of lists using collections module.

**Path taken:** attempt_1_pass

**Solution:**
```python
from collections import Counter

def freq_element(nested_list):
    # Flatten the list of lists into a single list
    flat_list = [item for sublist in nested_list for item in sublist]
    # Use Counter to count the frequency of each element
    freq = Counter(flat_list)
    # Sort the dictionary by frequency in descending order
    return dict(sorted(freq.items(), key=lambda x: x[1], reverse=True))
```

**Attempts:** 1

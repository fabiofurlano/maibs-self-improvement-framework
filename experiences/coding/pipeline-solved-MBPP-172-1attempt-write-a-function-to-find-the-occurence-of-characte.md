# Pipeline Solve — 2026-06-10 23:50

**Task:** Write a function to find the occurence of characters 'std' in the given string 1. list item 1. list item 1. list item 2. list item 2. list item 2. list item

**Path taken:** attempt_1_pass

**Solution:**
```python
def count_occurance(string):
    count = 0
    for i in range(len(string) - 2):
        if string[i:i+3] == 'std':
            count += 1
    return count
```

**Attempts:** 1

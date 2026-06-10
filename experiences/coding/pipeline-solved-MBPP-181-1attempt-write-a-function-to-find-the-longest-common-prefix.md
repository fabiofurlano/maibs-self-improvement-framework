# Pipeline Solve — 2026-06-10 23:54

**Task:** Write a function to find the longest common prefix in the given set of strings.

**Path taken:** attempt_1_pass

**Solution:**
```python
def common_prefix(strings, n):
    if not strings or n == 0:
        return ""
    
    # Use only the first n strings
    strings = strings[:n]
    
    if len(strings) == 1:
        return strings[0]
    
    # Find the length of the shortest string
    min_len = min(len(s) for s in strings)
    
    prefix = []
    for i in range(min_len):
        char = strings[0][i]
        # Check if this character is common to all strings at position i
        if all(s[i] == char for s in strings):
            prefix.append(char)
        else:
            break
    
    return "".join(prefix)
```

**Attempts:** 1

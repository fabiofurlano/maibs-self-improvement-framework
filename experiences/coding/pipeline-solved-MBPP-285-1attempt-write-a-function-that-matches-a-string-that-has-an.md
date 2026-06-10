# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function that matches a string that has an a followed by two to three 'b'.

**Path taken:** attempt_1_pass

**Solution:**
```python
import re

def text_match_two_three(text):
    patterns = 'ab{2,3}'
    if re.search(patterns, text):
        return ('Found a match!')
    else:
        return ('Not matched!')
```

**Attempts:** 1

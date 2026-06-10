# Pipeline Solve — 2026-06-10 23:52

**Task:** Write a function to remove specific words from a given list.

**Path taken:** attempt_1_pass

**Solution:**
```python
def remove_words(words, words_to_remove):
    return [word for word in words if word not in words_to_remove]
```

**Attempts:** 1

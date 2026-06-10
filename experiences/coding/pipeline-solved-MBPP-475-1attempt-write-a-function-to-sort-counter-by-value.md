# Pipeline Solve — 2026-06-10 23:43

**Task:** Write a function to sort counter by value.

**Path taken:** attempt_1_pass

**Solution:**
```python
def sort_counter(counter):
    return sorted(counter.items(), key=lambda x: x[1], reverse=True)
```

**Attempts:** 1

# Pipeline Solve — 2026-06-10 23:43

**Task:** Write a function to generate a 3d array having each element as '*'.

**Path taken:** attempt_1_pass

**Solution:**
```python
def array_3d(x, y, z):
    return [[['*'] * x for _ in range(y)] for _ in range(z)]
```

**Attempts:** 1

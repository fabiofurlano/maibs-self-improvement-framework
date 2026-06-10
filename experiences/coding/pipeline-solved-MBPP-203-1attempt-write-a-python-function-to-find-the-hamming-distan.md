# Pipeline Solve — 2026-06-10 23:59

**Task:** Write a python function to find the hamming distance between given two integers.

**Path taken:** attempt_1_pass

**Solution:**
```python
def hamming_Distance(n1, n2):
    # XOR the two numbers to find differing bits, then count the 1s
    return bin(n1 ^ n2).count('1')
```

**Attempts:** 1

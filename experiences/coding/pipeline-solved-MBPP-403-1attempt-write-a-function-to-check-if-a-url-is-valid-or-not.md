# Pipeline Solve — 2026-06-10 23:36

**Task:** Write a function to check if a url is valid or not using regex.

**Path taken:** attempt_1_pass

**Solution:**
```python
import re

def is_valid_URL(url):
    pattern = re.compile(
        r'^(https?://)?'                                  # optional http/https scheme
        r'((([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})'              # domain name (e.g., www.example.com)
        r'|(([0-9]{1,3}\.){3}[0-9]{1,3}))'                # OR IPv4 address
        r'(:[0-9]+)?'                                     # optional port
        r'(/[-a-zA-Z0-9@:%._\+~#?&//=]*)?'                # optional path, query, fragment
        r'$',
        re.IGNORECASE
    )
    return bool(pattern.match(url))
```

**Attempts:** 1

# Pipeline Solve — 2026-06-12 21:44

**Task:** Write a Python function fetch_page(url) that: 1. Uses requests.get() with timeout=10, 2. Catches requests.RequestException, ConnectionError, and invalid URL scheme, 3. Returns response.text on success

**Path taken:** intent:execute → safety_gate:GO → experience_index → attempt_1_pass

**Solution:**
```python
import requests

def fetch_page(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.RequestException:
        # Catches general requests exceptions, including ConnectionError and timeouts
        return None
    except ValueError:
        # This might catch issues related to invalid URL schemes if requests handles it this way,
        # though often requests raises a specific error for bad URLs.
        return None
```

**Attempts:** 1

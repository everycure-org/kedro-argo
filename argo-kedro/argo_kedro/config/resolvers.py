import secrets
import string

_random_cache = None

def random() -> str:
    """Generate a Kubernetes-like random suffix."""
    global _random_cache
    if _random_cache is None:
        size = max(1, int(6))
        _random_cache = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(size))
    
    return _random_cache


from slowapi import Limiter
from slowapi.util import get_remote_address

# Single limiter instance shared by all routers.
# key_func=get_remote_address → one bucket per client IP.
limiter = Limiter(key_func=get_remote_address)

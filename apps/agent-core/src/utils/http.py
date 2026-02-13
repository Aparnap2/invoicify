import httpx

# Persistent connection pool for all external API calls
# Configured for performance with keepalive and reasonable timeouts
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    timeout=httpx.Timeout(45.0, connect=10.0),
    # Follow redirects is often useful for static file downloads
    follow_redirects=True
)

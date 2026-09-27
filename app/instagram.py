"""Only official read endpoints and token refresh; no content publishing."""
import time
import logging
from urllib.parse import urlsplit
import httpx
from . import config

# Refresh uses the platform's mandated query token. HTTP client INFO logs include
# full URLs, so suppress these even when the worker's own logger uses INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class PlatformError(Exception):
    def __init__(self, message, retry=True, auth=False, delay=0):
        super().__init__(message)
        self.retry, self.auth, self.delay = retry, auth, delay

class Instagram:
    def __init__(self, token, client=None):
        self.token = token
        self.client = client or httpx.Client(timeout=httpx.Timeout(25), follow_redirects=False)

    def close(self):
        self.client.close()

    def get(self, path, params=None):
        try:
            response = self.client.get(f"https://graph.instagram.com/{config.API_VERSION}/{path.lstrip('/')}", params=params or {}, headers={"Authorization":f"Bearer {self.token}"})
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise PlatformError("Instagram ist momentan nicht erreichbar.") from None
        if response.is_error or "error" in data:
            error = data.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            if code == 190 or response.status_code == 401:
                raise PlatformError("Instagram-Zugang abgelaufen oder widerrufen. Bitte neu verbinden.", retry=False, auth=True)
            if response.status_code == 429 or code in (4, 17, 32, 613):
                try:
                    delay = max(60, min(int(response.headers.get("Retry-After", "900")), 86400))
                except ValueError:
                    delay = 900
                raise PlatformError("Instagram begrenzt die Abrufe. Der Hub wartet automatisch.", delay=delay)
            if response.status_code >= 500:
                raise PlatformError("Instagram meldet eine vorübergehende Störung.")
            raise PlatformError("Kennzahl oder Berechtigung nicht verfügbar.", retry=False)
        return data

    def identity(self):
        return self.get("me", {"fields":"user_id,username"})

    def publications(self, account_id, cursor=None):
        params = {"fields":"id,caption,media_type,media_product_type,permalink,timestamp,media_url,thumbnail_url", "limit":50}
        if cursor:
            params["after"] = cursor
        return self.get(f"{account_id}/media", params)

    def metric(self, external_id, name, params=None):
        return self.get(f"{external_id}/insights", {"metric":name, **(params or {})})

    def refresh(self):
        try:
            response = self.client.get("https://graph.instagram.com/refresh_access_token", params={"grant_type":"ig_refresh_token", "access_token":self.token})
            data = response.json()
            if response.status_code == 429 or response.status_code >= 500:
                raise PlatformError("Tokenverlängerung vorübergehend nicht erreichbar.")
            if response.is_error or not data.get("access_token"):
                raise PlatformError("Token konnte nicht verlängert werden. Verbindung prüfen.", retry=False, auth=True)
            return data
        except (httpx.HTTPError, ValueError):
            raise PlatformError("Tokenverlängerung vorübergehend nicht erreichbar.") from None

def safe_preview(url):
    if not url:
        return None
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return url if parsed.scheme == "https" and not parsed.username and (host.endswith(".cdninstagram.com") or host.endswith(".fbcdn.net")) else None

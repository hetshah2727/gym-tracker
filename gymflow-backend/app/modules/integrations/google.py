"""Google Search Console + Google Business Profile via OAuth 2.0 and the official REST APIs.

Nothing here is simulated: if GOOGLE_CLIENT_ID/SECRET are missing the connection reports
"not configured", and a gym is only "connected" after a successful token exchange AND the owner
selected a property/location they are authorised for.
"""
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.tenant_context import get_current_gym_id
from app.database.models import IntegrationConnection, SearchPerformance
from app.database.models.enums import ConnectionStatus
from app.database.repositories.base import TenantRepository

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GSC_API = "https://www.googleapis.com/webmasters/v3"
GBP_ACCOUNTS_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
GBP_INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_V4_API = "https://mybusiness.googleapis.com/v4"
GBP_READ_MASK = ("name,title,storefrontAddress,websiteUri,phoneNumbers,categories,regularHours,specialHours,"
                 "profile,serviceItems,openInfo,metadata,serviceArea")

PROVIDERS = {
    "google_search_console": {"label": "Google Search Console",
                              "scopes": ["https://www.googleapis.com/auth/webmasters.readonly"]},
    "google_business_profile": {"label": "Google Business Profile",
                                "scopes": ["https://www.googleapis.com/auth/business.manage"]},
}


class GoogleAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def is_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def redirect_uri() -> str:
    return settings.GOOGLE_OAUTH_REDIRECT_URI or f"{settings.PUBLIC_API_URL.rstrip('/')}/integrations/google/callback"


def request(method: str, url: str, **kwargs) -> httpx.Response:
    """Single HTTP entry point (tests monkeypatch this)."""
    return httpx.request(method, url, timeout=20, **kwargs)


def connection(db: Session, provider: str, create: bool = False) -> IntegrationConnection | None:
    repo = TenantRepository(IntegrationConnection, db)
    conn = repo.first(IntegrationConnection.provider == provider)
    if conn is None and create:
        conn = repo.add(provider=provider, status=ConnectionStatus.NOT_CONNECTED, scopes=[], settings={})
    return conn


# ---------------------------------------------------------------- OAuth

def authorization_url(provider: str, user_id: uuid.UUID) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown provider")
    if not is_configured():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Google OAuth is not configured on this server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).")
    state = jwt.encode({"purpose": "google_oauth", "provider": provider, "gym_id": str(get_current_gym_id()),
                        "user_id": str(user_id), "nonce": secrets.token_urlsafe(8),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                       settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    params = {"client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri(), "response_type": "code",
              "scope": " ".join(PROVIDERS[provider]["scopes"]), "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true", "state": state}
    return f"{AUTH_URL}?{urlencode(params)}"


def decode_state(state: str) -> dict:
    try:
        data = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state") from exc
    if data.get("purpose") != "google_oauth" or data.get("provider") not in PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")
    return data


def _store_tokens(conn: IntegrationConnection, token: dict) -> None:
    old = decrypt_json(conn.encrypted_tokens)
    merged = {"access_token": token["access_token"],
              "refresh_token": token.get("refresh_token") or old.get("refresh_token"),
              "token_type": token.get("token_type", "Bearer")}
    conn.encrypted_tokens = encrypt_json(merged)
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 3600)) - 60)
    if token.get("scope"):
        conn.scopes = token["scope"].split()


def exchange_code(db: Session, provider: str, code: str, user_id: uuid.UUID) -> IntegrationConnection:
    resp = request("POST", TOKEN_URL, data={"code": code, "client_id": settings.GOOGLE_CLIENT_ID,
                                            "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                            "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    conn = connection(db, provider, create=True)
    if resp.status_code != 200:
        conn.status, conn.last_error = ConnectionStatus.ERROR, f"Token exchange failed ({resp.status_code})"
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google did not accept the authorisation code")
    _store_tokens(conn, resp.json())
    conn.connected_by_id = user_id
    conn.status, conn.last_error = ConnectionStatus.PENDING, None
    db.flush()
    try:
        conn.settings = {**(conn.settings or {}), "available": list_choices(db, conn)}
    except GoogleAPIError as exc:
        conn.last_error = str(exc)
    db.commit()
    return conn


def access_token(db: Session, conn: IntegrationConnection) -> str:
    tokens = decrypt_json(conn.encrypted_tokens)
    if not tokens.get("access_token"):
        raise GoogleAPIError("Not connected")
    expires = conn.token_expires_at
    if expires and (expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        conn.status, conn.last_error = ConnectionStatus.EXPIRED, "Access expired; reconnect Google"
        db.commit()
        raise GoogleAPIError("Access expired; reconnect Google", 401)
    resp = request("POST", TOKEN_URL, data={"client_id": settings.GOOGLE_CLIENT_ID,
                                            "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                            "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
    if resp.status_code != 200:
        conn.status, conn.last_error = ConnectionStatus.EXPIRED, "Google refused to refresh access; reconnect"
        db.commit()
        raise GoogleAPIError("Google access expired; reconnect", 401)
    _store_tokens(conn, resp.json())
    db.commit()
    return decrypt_json(conn.encrypted_tokens)["access_token"]


def api(db: Session, conn: IntegrationConnection, method: str, url: str, **kwargs) -> dict:
    token = access_token(db, conn)
    resp = request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
    if resp.status_code in (401, 403):
        conn.last_error = f"Google returned {resp.status_code}: permission denied"
        if resp.status_code == 401:
            conn.status = ConnectionStatus.EXPIRED
        db.commit()
        raise GoogleAPIError(conn.last_error, resp.status_code)
    if resp.status_code >= 400:
        raise GoogleAPIError(f"Google API error {resp.status_code}: {resp.text[:200]}", resp.status_code)
    return resp.json() if resp.content else {}


def list_choices(db: Session, conn: IntegrationConnection) -> list[dict]:
    if conn.provider == "google_search_console":
        sites = api(db, conn, "GET", f"{GSC_API}/sites").get("siteEntry", [])
        return [{"id": s["siteUrl"], "label": s["siteUrl"], "permission": s.get("permissionLevel")}
                for s in sites if s.get("permissionLevel") != "siteUnverifiedUser"]
    choices = []
    for account in api(db, conn, "GET", f"{GBP_ACCOUNTS_API}/accounts").get("accounts", [])[:5]:
        data = api(db, conn, "GET", f"{GBP_INFO_API}/{account['name']}/locations",
                   params={"readMask": "name,title,storefrontAddress", "pageSize": 100})
        for loc in data.get("locations", []):
            address = loc.get("storefrontAddress") or {}
            choices.append({"id": f"{account['name']}/{loc['name']}", "label": loc.get("title"),
                            "address": ", ".join(address.get("addressLines", []) + [address.get("locality", "")])})
    return choices


def select(db: Session, provider: str, external_id: str) -> IntegrationConnection:
    conn = connection(db, provider)
    if conn is None or not conn.encrypted_tokens:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect Google first")
    allowed = {c["id"]: c for c in (conn.settings or {}).get("available", [])}
    if external_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That property/location is not available to this Google account")
    conn.external_id, conn.account_label = external_id, allowed[external_id].get("label")
    conn.status, conn.last_error = ConnectionStatus.CONNECTED, None
    db.commit()
    return conn


def disconnect(db: Session, provider: str) -> None:
    conn = connection(db, provider)
    if conn is None:
        return
    token = decrypt_json(conn.encrypted_tokens).get("refresh_token") or decrypt_json(conn.encrypted_tokens).get(
        "access_token")
    if token:
        try:
            request("POST", REVOKE_URL, params={"token": token})
        except httpx.HTTPError:
            logger.warning("Google token revoke failed for gym %s", conn.gym_id)
    conn.encrypted_tokens, conn.token_expires_at, conn.external_id = None, None, None
    conn.status, conn.settings, conn.account_label = ConnectionStatus.NOT_CONNECTED, {}, None
    db.commit()


def require_connected(db: Session, provider: str) -> IntegrationConnection:
    conn = connection(db, provider)
    if conn is None or conn.status != ConnectionStatus.CONNECTED or not conn.external_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{PROVIDERS[provider]['label']} is not connected")
    return conn


# ---------------------------------------------------------------- Search Console

def sync_search_console(db: Session, days: int = 28) -> int:
    conn = require_connected(db, "google_search_console")
    end = date.today() - timedelta(days=2)  # GSC data lags ~2 days
    start = end - timedelta(days=days - 1)
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["date", "query", "page"],
            "rowLimit": 5000}
    try:
        data = api(db, conn, "POST", f"{GSC_API}/sites/{quote(conn.external_id, safe='')}/searchAnalytics/query",
                   json=body)
    except GoogleAPIError as exc:
        conn.last_error = str(exc)
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    gym_id = get_current_gym_id()
    db.execute(delete(SearchPerformance).where(SearchPerformance.gym_id == gym_id, SearchPerformance.day >= start,
                                               SearchPerformance.day <= end,
                                               SearchPerformance.source == "google_search_console"))
    rows = data.get("rows", [])
    for row in rows:
        d, query, page = (row.get("keys") or [None, None, None])[:3]
        db.add(SearchPerformance(gym_id=gym_id, day=date.fromisoformat(d), query=(query or "")[:500],
                                 page=(page or "")[:1000], clicks=int(row.get("clicks", 0)),
                                 impressions=int(row.get("impressions", 0)), ctr=float(row.get("ctr", 0)),
                                 position=float(row.get("position", 0)), source="google_search_console"))
    conn.last_sync_at, conn.last_error = datetime.now(timezone.utc), None
    db.commit()
    return len(rows)


# ---------------------------------------------------------------- Business Profile

def _location_parts(external_id: str) -> tuple[str, str]:
    account, location = external_id.split("/locations/", 1)
    return account, f"locations/{location}"


def fetch_location(db: Session) -> dict:
    conn = require_connected(db, "google_business_profile")
    _, location = _location_parts(conn.external_id)
    return api(db, conn, "GET", f"{GBP_INFO_API}/{location}", params={"readMask": GBP_READ_MASK})


def fetch_reviews(db: Session, page_size: int = 50) -> dict:
    conn = require_connected(db, "google_business_profile")
    return api(db, conn, "GET", f"{GBP_V4_API}/{conn.external_id}/reviews", params={"pageSize": page_size})


def reply_to_review(db: Session, review_id: str, comment: str) -> dict:
    conn = require_connected(db, "google_business_profile")
    return api(db, conn, "PUT", f"{GBP_V4_API}/{conn.external_id}/reviews/{quote(review_id, safe='')}/reply",
               json={"comment": comment})


def create_local_post(db: Session, text: str, call_to_action: str | None, url: str | None) -> dict:
    conn = require_connected(db, "google_business_profile")
    body: dict = {"languageCode": "en-IN", "summary": text[:1500], "topicType": "STANDARD"}
    if call_to_action and call_to_action != "CALL" and url:
        body["callToAction"] = {"actionType": call_to_action, "url": url}
    elif call_to_action == "CALL":
        body["callToAction"] = {"actionType": "CALL"}
    return api(db, conn, "POST", f"{GBP_V4_API}/{conn.external_id}/localPosts", json=body)


def normalize_location(loc: dict, reviews: dict | None = None) -> dict:
    """Map the Business Information API shape to GymFlow's profile-audit fields."""
    address = loc.get("storefrontAddress") or {}
    categories = loc.get("categories") or {}
    periods = (loc.get("regularHours") or {}).get("periods", [])
    return {
        "name": loc.get("title"),
        "primary_category": (categories.get("primaryCategory") or {}).get("displayName"),
        "additional_categories": [c.get("displayName") for c in categories.get("additionalCategories", [])],
        "description": (loc.get("profile") or {}).get("description"),
        "address": ", ".join([*address.get("addressLines", []), address.get("locality", ""),
                              address.get("administrativeArea", ""), address.get("postalCode", "")]).strip(", "),
        "phone": (loc.get("phoneNumbers") or {}).get("primaryPhone"),
        "website": loc.get("websiteUri"),
        "hours": [{"day": p.get("openDay"), "opens": _hm(p.get("openTime")), "closes": _hm(p.get("closeTime"))}
                  for p in periods],
        "special_hours_count": len((loc.get("specialHours") or {}).get("specialHourPeriods", [])),
        "services": [((s.get("freeFormServiceItem") or {}).get("label") or {}).get("displayName")
                     or (s.get("structuredServiceItem") or {}).get("serviceTypeId") for s in loc.get("serviceItems", [])],
        "attributes": None,          # needs the separate attributes endpoint; reported as unavailable
        "photos_count": None,        # media API not used; reported as unavailable
        "review_count": (reviews or {}).get("totalReviewCount"),
        "rating": (reviews or {}).get("averageRating"),
        "maps_uri": (loc.get("metadata") or {}).get("mapsUri"),
        "new_review_uri": (loc.get("metadata") or {}).get("newReviewUri"),
        "open_status": (loc.get("openInfo") or {}).get("status"),
    }


def _hm(t: dict | None) -> str | None:
    if not t:
        return None
    return f"{int(t.get('hours', 0)):02d}:{int(t.get('minutes', 0)):02d}"

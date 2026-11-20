"""Amazon Associates link builder."""
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.config import settings


def build_affiliate_url(external_url: str, asin: str | None = None, tag: str | None = None,
                        sub_tag: str | None = None) -> str:
    """Add the Associates tag, plus ``ascsubtag`` so earnings reports can be
    matched back to the GymFlow link (and therefore gym + trainer)."""
    tag = tag or settings.AMAZON_ASSOCIATE_TAG
    if asin:
        external_url = f"https://{settings.AMAZON_MARKETPLACE_DOMAIN}/dp/{asin}"
    parts = urlparse(external_url)
    query = dict(parse_qsl(parts.query))
    if tag:
        query["tag"] = tag
    if sub_tag:
        query["ascsubtag"] = sub_tag
    return urlunparse(parts._replace(query=urlencode(query)))

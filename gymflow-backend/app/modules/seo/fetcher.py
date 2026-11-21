"""SSRF-safe HTTP fetching for the SEO crawler.

Defences:
* only http/https, only ports 80/443, no credentials in URLs;
* hostnames like localhost, *.internal, *.local and cloud metadata names are refused;
* every address the hostname resolves to must be a public (globally routable) IP - private,
  loopback, link-local (169.254.169.254 metadata), CGNAT, multicast and reserved ranges are refused;
* redirects are followed manually (max 5) and every hop is re-validated;
* after connecting, the peer address is checked again (narrows DNS-rebinding) before the body is read;
* response bodies are capped and requests time out.
"""
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings

BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal", "instance-data",
                     "metadata.azure.com", "kubernetes.default", "kubernetes.default.svc"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home.arpa", ".svc",
                    ".cluster.local")
ALLOWED_PORTS = {None, 80, 443}
MAX_REDIRECTS = 5

Resolver = Callable[[str], list[str]]


class UnsafeUrlError(ValueError):
    pass


def default_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve {host}") from exc
    return list({info[4][0] for info in infos})


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local
                                 or ip.is_private or ip.is_unspecified)


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise UnsafeUrlError("Enter a website address")
    if "://" not in raw:
        raw = "https://" + raw
    return raw


def validate_url(url: str, resolver: Resolver | None = None) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http and https websites can be audited")
    if parts.username or parts.password:
        raise UnsafeUrlError("URLs with credentials are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeUrlError("The URL has no host name")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("Invalid port") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("Only standard web ports (80/443) are allowed")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES) or "." not in host:
        raise UnsafeUrlError("That host name is not allowed")
    try:  # literal IP in the URL
        ipaddress.ip_address(host.strip("[]"))
        addresses = [host.strip("[]")]
    except ValueError:
        addresses = (resolver or default_resolver)(host)
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise UnsafeUrlError("That address points to a private or internal network")
    return url


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    redirect_chain: list = field(default_factory=list)
    elapsed_ms: int = 0
    truncated: bool = False
    error: str | None = None

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").lower()

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type

    def text(self) -> str:
        charset = "utf-8"
        if "charset=" in self.content_type:
            charset = self.content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class SafeFetcher:
    def __init__(self, *, timeout: float | None = None, max_bytes: int | None = None,
                 user_agent: str | None = None, resolver: Resolver | None = None,
                 transport: httpx.BaseTransport | None = None, check_peer: bool = True):
        self.timeout = timeout or settings.SEO_REQUEST_TIMEOUT
        self.max_bytes = max_bytes or settings.SEO_MAX_PAGE_BYTES
        self.user_agent = user_agent or settings.SEO_USER_AGENT
        self.resolver = resolver
        self.check_peer = check_peer and transport is None
        self.client = httpx.Client(timeout=self.timeout, follow_redirects=False, transport=transport,
                                   headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*;q=0.8"})
        self.requests = 0

    def close(self) -> None:
        self.client.close()

    def _peer_ok(self, response: httpx.Response) -> bool:
        stream = response.extensions.get("network_stream")
        if stream is None:
            return True
        try:
            addr = stream.get_extra_info("server_addr")
        except Exception:  # noqa: BLE001
            return True
        return not addr or is_public_ip(str(addr[0]))

    def fetch(self, url: str, method: str = "GET", max_bytes: int | None = None) -> FetchResult:
        limit = max_bytes or self.max_bytes
        result = FetchResult(url=url, final_url=url)
        current = url
        started = time.monotonic()
        for _ in range(MAX_REDIRECTS + 1):
            try:
                validate_url(current, self.resolver)
            except UnsafeUrlError as exc:
                result.error = str(exc)
                return result
            self.requests += 1
            try:
                with self.client.stream(method, current) as resp:
                    if self.check_peer and not self._peer_ok(resp):
                        result.error = "Connection resolved to a private address"
                        return result
                    if resp.is_redirect and resp.headers.get("location"):
                        nxt = urljoin(current, resp.headers["location"])
                        result.redirect_chain.append({"url": current, "status": resp.status_code})
                        current = nxt
                        continue
                    body = bytearray()
                    if method != "HEAD":
                        for chunk in resp.iter_bytes():
                            body.extend(chunk)
                            if len(body) > limit:
                                result.truncated = True
                                break
                    result.status = resp.status_code
                    result.headers = {k.lower(): v for k, v in resp.headers.items()}
                    result.body = bytes(body[:limit])
                    result.final_url = current
                    result.elapsed_ms = int((time.monotonic() - started) * 1000)
                    return result
            except httpx.HTTPError as exc:
                result.error = f"{type(exc).__name__}: {exc}"[:300]
                result.final_url = current
                result.elapsed_ms = int((time.monotonic() - started) * 1000)
                return result
        result.error = "Too many redirects"
        return result

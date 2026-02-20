"""
Source provider abstraction for canopyresearch.

Providers fetch raw documents and normalize them to the internal schema.
The pipeline owns validation, hashing, deduplication, and persistence.
"""

import hashlib
import ipaddress
import os
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from django.utils import timezone
from lxml import html as lxml_html
from readability import Document as ReadabilityDocument

from canopyresearch.models import Source

# Internal normalized document schema (all providers must output this)
NORMALIZED_SCHEMA_KEYS = {"external_id", "title", "url", "content", "published_at", "metadata"}

USER_AGENT = "canopy-research/0.1"
HTTP_TIMEOUT = 30
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB max response size


def _is_url_allowed(url: str) -> bool:
    """
    Check if URL is allowed against DENY patterns.

    Blocks:
    - Direct IP addresses (IPv4 and IPv6)
    - Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Loopback addresses (127.0.0.0/8, ::1)
    - Link-local addresses (169.254.0.0/16, fe80::/10)

    Returns True if URL is allowed, False if denied.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        # Block literal hostname "localhost" (no IP form)
        if hostname.lower() == "localhost":
            return False

        # Handle IPv6 addresses in brackets (urlparse may already strip them)
        if hostname.startswith("[") and hostname.endswith("]"):
            hostname = hostname[1:-1]

        # Remove port only when it's IPv4:port (exactly one colon). IPv6 addresses
        # contain colons, so splitting on ':' would truncate them (e.g. '::1' -> '').
        if hostname.count(":") == 1:
            hostname = hostname.split(":")[0]

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)

            # DENY: Block private, loopback, link-local, and reserved IPs
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False

            # DENY: All direct IP addresses (even public ones) are blocked
            return False
        except ValueError:
            # Not an IP address, might be a hostname - allow it
            pass

        # Check for IP patterns in hostname (e.g., "127.0.0.1.example.com").
        # Single segments like "127" are not valid IPs, so check every 4 consecutive
        # segments for IPv4.
        parts = hostname.split(".")
        for i in range(len(parts) - 3):
            quad = ".".join(parts[i : i + 4])
            try:
                ipaddress.ip_address(quad)
                return False
            except ValueError:
                continue

        return True
    except Exception:
        # On any parsing error, deny to be safe
        return False


def extract_article_content(url: str) -> str | None:
    """
    Fetch URL and extract main article content using readability.

    Validates URL against DENY patterns and enforces max response size.

    Returns plain text or None on failure. Caller should fall back to snippet.
    """
    # Validate URL against DENY patterns
    if not _is_url_allowed(url):
        return None

    try:
        # Stream response with max bytes cap
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, stream=True
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None

        # Stream response content with size limit
        content_chunks = []
        total_size = 0

        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                total_size += len(chunk)
                if total_size > MAX_RESPONSE_SIZE:
                    # Response exceeds max size, abort
                    return None
                content_chunks.append(chunk)

        # Combine chunks
        html_bytes = b"".join(content_chunks)

        try:
            html = html_bytes.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, AttributeError):
            return None

        doc = ReadabilityDocument(html)
        summary_html = doc.summary()
        if not summary_html or not summary_html.strip():
            return None
        tree = lxml_html.fromstring(summary_html)
        text = tree.text_content() if tree is not None else ""
        return text.strip() if text else None
    except (
        requests.RequestException,
        ValueError,
        TypeError,
    ):
        return None


def _extract_links_from_html(
    html: str, skip_same_domain: str | None = None
) -> list[tuple[str, str]]:
    """
    Extract http(s) links from HTML, optionally skipping same-domain links.

    Uses lxml to parse HTML and extract links in a single operation,
    similar to Nokogiri's doc.all("a").map { |link| [link["href"], link.text] }
    """
    if not html or not html.strip():
        return []

    try:
        tree = lxml_html.fromstring(html)
    except (ValueError, TypeError, lxml_html.etree.ParserError):
        return []

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    base_domain = urlparse(skip_same_domain).netloc if skip_same_domain else None

    # Find all anchor tags with href attributes
    for anchor in tree.xpath("//a[@href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue

        # Only include http/https URLs
        if not (href.startswith("http://") or href.startswith("https://")):
            continue

        # Skip duplicates
        if href in seen:
            continue

        # Skip same-domain links if requested
        if skip_same_domain and base_domain:
            link_domain = urlparse(href).netloc
            if link_domain == base_domain:
                continue

        # Extract link text (all text content within the anchor tag)
        link_text = anchor.text_content().strip()

        seen.add(href)
        result.append((href, link_text or href))

    return result


class BaseSourceProvider:
    """
    Abstract base class for any content provider.

    Providers fetch raw documents and normalize them.
    Subclasses must implement fetch() and normalize().
    """

    provider_type: str = "base"

    def __init__(self, source: Source):
        self.source = source

    def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch and return raw provider documents.

        Returns provider-specific structure. Each raw doc will be passed to normalize().
        """
        raise NotImplementedError("Subclasses must implement fetch()")

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """
        Convert raw provider document to normalized schema.

        Must return dict with keys: external_id, title, url, content, published_at, metadata.
        """
        raise NotImplementedError("Subclasses must implement normalize()")


def _entry_to_raw(entry: Any) -> dict[str, Any]:
    """Convert feedparser entry to raw dict for normalize."""
    link = getattr(entry, "link", "") or ""
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    return {
        "id": getattr(entry, "id", None),
        "guid": getattr(entry, "guid", None),
        "title": getattr(entry, "title", "") or "",
        "link": link,
        "summary": summary,
        "description": getattr(entry, "description", "") or summary,
        "published": getattr(entry, "published", None),
        "published_parsed": getattr(entry, "published_parsed", None),
        "author": getattr(entry, "author", None),
        "tags": getattr(entry, "tags", []) or [],
    }


class RSSProvider(BaseSourceProvider):
    """Provider for RSS feed sources."""

    provider_type = "rss"

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw documents from an RSS feed."""
        config = self.source.config or {}
        url = config.get("url")
        if not url:
            return []

        fetch_full_article = config.get("fetch_full_article", True)
        extract_body_links = config.get("extract_body_links", False)
        emit_newsletter_entry = config.get("emit_newsletter_entry", False)
        max_links_per_entry = config.get("max_links_per_entry", 50)
        skip_same_domain = config.get("skip_same_domain")  # entry link for same-domain check

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            raise

        parsed = feedparser.parse(resp.content)
        raw_docs: list[dict[str, Any]] = []

        for entry in parsed.entries:
            if extract_body_links:
                body = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                entry_link = getattr(entry, "link", "") or ""
                base = skip_same_domain if skip_same_domain else entry_link
                links = _extract_links_from_html(body, skip_same_domain=base)[:max_links_per_entry]
                for link_url, link_text in links:
                    raw = {
                        "link": link_url,
                        "title": link_text or link_url,
                        "id": hashlib.sha256(link_url.encode()).hexdigest()[:16],
                        "guid": link_url,
                        "summary": "",
                        "description": "",
                        "published": getattr(entry, "published", None),
                        "published_parsed": getattr(entry, "published_parsed", None),
                        "author": getattr(entry, "author", None),
                        "tags": [],
                        "metadata": {"from_entry": getattr(entry, "title", "") or ""},
                    }
                    if fetch_full_article and link_url:
                        extracted = extract_article_content(link_url)
                        if extracted:
                            raw["extracted_content"] = extracted
                    raw_docs.append(raw)
                if emit_newsletter_entry:
                    raw_docs.append(_entry_to_raw(entry))
            else:
                raw = _entry_to_raw(entry)
                if fetch_full_article and raw.get("link"):
                    extracted = extract_article_content(raw["link"])
                    if extracted:
                        raw["extracted_content"] = extracted
                raw_docs.append(raw)

        return raw_docs

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert RSS entry to normalized schema."""
        published = raw_doc.get("published_parsed") or raw_doc.get("published")
        if isinstance(published, datetime):
            published_at = (
                timezone.make_aware(published) if timezone.is_naive(published) else published
            )
        elif hasattr(published, "tm_year"):  # time.struct_time from feedparser
            from datetime import timezone as dt_tz

            dt = datetime(*published[:6])
            published_at = timezone.make_aware(dt, dt_tz.utc)
        else:
            published_at = timezone.now()

        content = raw_doc.get("extracted_content")
        if not content:
            content = raw_doc.get("summary", "") or raw_doc.get("description", "")

        metadata = dict(raw_doc.get("metadata", {}))
        if "author" not in metadata:
            metadata["author"] = raw_doc.get("author")
        if "tags" not in metadata:
            metadata["tags"] = raw_doc.get("tags", [])

        return {
            "external_id": str(raw_doc.get("id") or raw_doc.get("guid") or ""),
            "title": raw_doc.get("title", ""),
            "url": raw_doc.get("link", ""),
            "content": content or "",
            "published_at": published_at,
            "metadata": metadata,
        }


class HackerNewsProvider(BaseSourceProvider):
    """Provider for Hacker News sources."""

    provider_type = "hackernews"

    def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch raw documents from Hacker News via Algolia API.

        Supports filtering options in config:
        - min_points: Minimum points threshold (e.g., 50)
        - min_comments: Minimum comments threshold (e.g., 10)
        - query: Keyword search query (searches title and URL)
        - listing: "front_page" (default), "new", "ask_hn", "show_hn"
        - limit: Maximum number of results (default 50, max 100)
        """
        config = self.source.config or {}
        listing = config.get("listing", "front_page")
        limit = min(config.get("limit", 50), 100)
        tags_override = config.get("tags")
        fetch_full_article = config.get("fetch_full_article", True)

        # Filtering options
        min_points = config.get("min_points")
        min_comments = config.get("min_comments")
        query = config.get("query", "").strip()

        if tags_override:
            tags = tags_override[0] if isinstance(tags_override, list) else str(tags_override)
        elif listing == "new":
            tags = "story"
            endpoint = "search_by_date"
        elif listing == "ask_hn":
            tags = "ask_hn"
            endpoint = "search"
        elif listing == "show_hn":
            tags = "show_hn"
            endpoint = "search"
        else:
            tags = "story"
            endpoint = "search"

        # Build URL with filters
        params = [f"tags={tags}", f"hitsPerPage={limit}"]

        # Add keyword query if provided
        if query:
            from urllib.parse import quote

            params.append(f"query={quote(query)}")

        # Add numeric filters for points and comments
        numeric_filters = []
        if min_points is not None:
            numeric_filters.append(f"points>={min_points}")
        if min_comments is not None:
            numeric_filters.append(f"num_comments>={min_comments}")

        if numeric_filters:
            params.append(f"numericFilters={','.join(numeric_filters)}")

        url = f"https://hn.algolia.com/api/v1/{endpoint}?{'&'.join(params)}"

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            raise

        hits = data.get("hits", [])
        raw_docs: list[dict[str, Any]] = []

        for hit in hits:
            raw: dict[str, Any] = {
                "id": hit.get("objectID") or hit.get("story_id"),
                "objectID": hit.get("objectID"),
                "story_id": hit.get("story_id"),
                "title": hit.get("title", ""),
                "url": hit.get("url"),
                "author": hit.get("author"),
                "points": hit.get("points", 0),
                "num_comments": hit.get("num_comments", 0),
                "created_at_i": hit.get("created_at_i"),
                "text": hit.get("story_text") or hit.get("title", ""),
            }
            if (
                fetch_full_article
                and raw.get("url")
                and "news.ycombinator.com" not in str(raw["url"])
            ):
                extracted = extract_article_content(str(raw["url"]))
                if extracted:
                    raw["extracted_content"] = extracted
            raw_docs.append(raw)

        return raw_docs

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert HN item to normalized schema. Supports both Algolia and Firebase shapes."""
        from datetime import datetime as dt
        from datetime import timezone as dt_tz

        time_val = raw_doc.get("created_at_i") or raw_doc.get("time")
        if time_val is not None:
            published_at = dt.fromtimestamp(time_val, tz=dt_tz.utc)
        else:
            published_at = timezone.now()

        item_id = raw_doc.get("objectID") or raw_doc.get("story_id") or raw_doc.get("id", "")
        url = raw_doc.get("url")
        if url is None or (isinstance(url, str) and "news.ycombinator.com" in url):
            url = f"https://news.ycombinator.com/item?id={item_id}"

        content = raw_doc.get("extracted_content")
        if not content:
            content = raw_doc.get("text", "") or raw_doc.get("title", "")

        return {
            "external_id": str(item_id),
            "title": raw_doc.get("title", ""),
            "url": str(url) if url else "",
            "content": content or raw_doc.get("title", ""),
            "published_at": published_at,
            "metadata": {
                "by": raw_doc.get("author") or raw_doc.get("by"),
                "score": raw_doc.get("points") or raw_doc.get("score"),
                "type": raw_doc.get("type"),
                "num_comments": raw_doc.get("num_comments"),
            },
        }


def _reddit_refresh_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Obtain access token via Reddit OAuth2 refresh token."""
    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(client_id, client_secret),
        headers={"User-Agent": USER_AGENT},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


class SubredditProvider(BaseSourceProvider):
    """Provider for Reddit subreddit sources."""

    provider_type = "subreddit"

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw documents from a Reddit subreddit."""
        config = self.source.config or {}
        subreddit = config.get("subreddit")
        if not subreddit:
            return []

        listing = config.get("listing", "hot")
        limit = min(config.get("limit", 100), 100)
        timeframe = config.get("timeframe", "week")
        fetch_full_article = config.get("fetch_full_article", True)

        client_id = config.get("client_id") or os.environ.get("REDDIT_CLIENT_ID")
        client_secret = config.get("client_secret") or os.environ.get("REDDIT_CLIENT_SECRET")
        refresh_token = config.get("refresh_token")
        access_token = config.get("access_token")
        expires_at = config.get("expires_at")

        use_oauth = bool(client_id and client_secret and (refresh_token or access_token))

        if use_oauth:
            if access_token and expires_at and datetime.now().timestamp() < expires_at:
                token = access_token
            elif refresh_token:
                token = _reddit_refresh_token(client_id, client_secret, refresh_token)
            else:
                return []

            base_url = "https://oauth.reddit.com"
            path = f"/r/{subreddit}/{listing}"
            qs = f"limit={limit}"
            if listing == "top":
                qs += f"&t={timeframe}"
            url = f"{base_url}{path}?{qs}"
            headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{listing}.json?limit={limit}&t={timeframe}"
            headers = {"User-Agent": USER_AGENT}

        try:
            resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            raise

        children = []
        if isinstance(data, dict):
            children = data.get("data", {}).get("children", [])
        raw_docs: list[dict[str, Any]] = []

        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            if not post:
                continue
            raw: dict[str, Any] = {
                "id": post.get("id"),
                "title": post.get("title", ""),
                "selftext": post.get("selftext", ""),
                "url": post.get("url", ""),
                "permalink": post.get("permalink", ""),
                "author": post.get("author"),
                "subreddit": post.get("subreddit"),
                "score": post.get("score"),
                "created_utc": post.get("created_utc"),
            }
            is_self = "reddit.com" in str(post.get("url", ""))
            if (
                fetch_full_article
                and not is_self
                and raw.get("url")
                and "reddit.com" not in str(raw["url"])
            ):
                extracted = extract_article_content(str(raw["url"]))
                if extracted:
                    raw["extracted_content"] = extracted
            raw_docs.append(raw)

        return raw_docs

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert Reddit post to normalized schema."""
        from datetime import datetime as dt
        from datetime import timezone as dt_tz

        created = raw_doc.get("created_utc")
        if created is not None:
            # created_utc is epoch seconds in UTC, so create UTC-aware datetime first
            published_at = dt.fromtimestamp(created, tz=dt_tz.utc)
            # Convert to default timezone for consistency with timezone.now()
            published_at = published_at.astimezone(timezone.get_default_timezone())
        else:
            published_at = timezone.now()

        content = raw_doc.get("extracted_content")
        if not content:
            content = raw_doc.get("selftext", "") or raw_doc.get("title", "")

        url = raw_doc.get("url") or ""
        if not url and raw_doc.get("permalink"):
            url = f"https://reddit.com{raw_doc['permalink']}"

        return {
            "external_id": raw_doc.get("id", ""),
            "title": raw_doc.get("title", ""),
            "url": url or "",
            "content": content or raw_doc.get("title", ""),
            "published_at": published_at,
            "metadata": {
                "author": raw_doc.get("author"),
                "subreddit": raw_doc.get("subreddit"),
                "score": raw_doc.get("score"),
            },
        }


PROVIDER_REGISTRY = {
    "rss": RSSProvider,
    "hackernews": HackerNewsProvider,
    "subreddit": SubredditProvider,
}


def get_provider_class(provider_type: str) -> type[BaseSourceProvider]:
    """
    Get the provider class for a given provider type.

    Raises:
        ValueError: If provider_type is not registered
    """
    provider_class = PROVIDER_REGISTRY.get(provider_type)
    if provider_class is None:
        raise ValueError(f"Unknown provider type: {provider_type}")
    return provider_class

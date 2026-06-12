"""Search-index traversal and pagination for OLX Pakistan."""

from __future__ import annotations

import logging
import random
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.olx.com.pk"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

PRODUCT_PATH_PATTERN = re.compile(r"/item/[^\s\"']+iid-\d+", re.IGNORECASE)


def build_search_url(keyword: str, page: int = 1) -> str:
    """Construct the localized keyword search URL for OLX Pakistan."""
    slug = keyword.strip().lower().replace(" ", "-")
    base = f"{BASE_URL}/items/q-{slug}/"
    if page <= 1:
        return base
    return f"{base}?page={page}"


def fetch_html(url: str, session: requests.Session | None = None) -> str:
    """Perform a throttled HTTP GET and return response text."""
    time.sleep(random.uniform(0, 5))

    http = session or requests.Session()
    response = http.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _normalize_product_url(href: str) -> str | None:
    """Convert relative OLX item links into absolute canonical URLs."""
    if "iid-" not in href:
        return None

    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = BASE_URL + href
    elif not href.startswith("http"):
        href = urljoin_path(href)

    if BASE_URL not in href:
        return None

    return href.split("?")[0].split("#")[0]


def urljoin_path(href: str) -> str:
    """Join a relative path to the OLX base URL."""
    if not href.startswith("/"):
        href = "/" + href
    return BASE_URL + href


def get_product_urls(
    page_url: str,
    session: requests.Session | None = None,
    html: str | None = None,
) -> list[str]:
    """
    Extract all product detail URLs from a search results page.
    Applies anti-bot throttle before the network request unless html is provided.
    """
    if html is None:
        try:
            html = fetch_html(page_url, session=session)
        except requests.RequestException as exc:
            logger.warning("Failed to fetch search page %s: %s", page_url, exc)
            return []

    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        normalized = _normalize_product_url(anchor["href"])
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    for match in PRODUCT_PATH_PATTERN.findall(html):
        normalized = _normalize_product_url(match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    return urls


def _current_page_number(page_url: str) -> int:
    """Parse the page query parameter, defaulting to 1."""
    parsed = urlparse(page_url)
    params = parse_qs(parsed.query)
    raw = params.get("page", ["1"])[0]
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _build_page_url(page_url: str, page_number: int) -> str:
    """Return the same search URL with an updated page query parameter."""
    parsed = urlparse(page_url)
    params = parse_qs(parsed.query)
    if page_number <= 1:
        params.pop("page", None)
    else:
        params["page"] = [str(page_number)]
    query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=query))


def get_next_page(
    page_url: str,
    html: str | None = None,
    session: requests.Session | None = None,
) -> str | None:
    """
    Locate the next pagination URL from the current search page.

    OLX renders numeric pagination; when an explicit next link is absent,
    the next page URL is synthesized by incrementing the page parameter.
    """
    if html is None:
        try:
            html = fetch_html(page_url, session=session)
        except requests.RequestException as exc:
            logger.warning("Failed to fetch page for pagination %s: %s", page_url, exc)
            return None

    soup = BeautifulSoup(html, "lxml")
    current_page = _current_page_number(page_url)

    next_selectors = [
        "a[aria-label='Next Page']",
        "a[aria-label='Next']",
        "a[rel='next']",
        "li.ant-pagination-next a",
        "a.pagination-next",
    ]
    for selector in next_selectors:
        link = soup.select_one(selector)
        if link and link.get("href"):
            normalized = _normalize_search_link(link["href"])
            if normalized:
                return normalized

    for anchor in soup.find_all("a", href=True):
        label = (anchor.get("aria-label") or "").strip().lower()
        text = anchor.get_text(strip=True).lower()
        if label == "next page" or text in {"next", ">", "›"}:
            normalized = _normalize_search_link(anchor["href"])
            if normalized:
                return normalized

    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if text.isdigit() and int(text) == current_page + 1:
            normalized = _normalize_search_link(anchor["href"])
            if normalized:
                return normalized

    return _build_page_url(page_url, current_page + 1)


def _normalize_search_link(href: str) -> str | None:
    """Normalize pagination links to absolute OLX URLs."""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = BASE_URL + href
    elif not href.startswith("http"):
        return None

    if BASE_URL not in href:
        return None
    return href.split("#")[0]

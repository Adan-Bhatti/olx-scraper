"""Detail-page parsing for OLX Pakistan product listings."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper import BASE_URL, USER_AGENT, fetch_html

logger = logging.getLogger(__name__)

PRODUCT_ID_PATTERN = re.compile(r"iid-([\w-]+)", re.IGNORECASE)
IMAGE_PATTERN = re.compile(
    r"https://images\.olx\.com\.pk/[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp)",
    re.IGNORECASE,
)


def extract_product_id(url: str, soup: BeautifulSoup | None = None) -> str | None:
    """Derive product_id from the OLX iid URL pattern or JSON-LD sku."""
    match = PRODUCT_ID_PATTERN.search(url)
    if match:
        return match.group(1)

    if soup is not None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                sku = data.get("sku")
                if sku:
                    return str(sku)
    return None


def _parse_price(value: str | float | int | None) -> float | None:
    """Convert a price string like 'Rs. 45,000' into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_json_ld_product(soup: BeautifulSoup) -> dict[str, Any]:
    """Read schema.org Product data embedded as JSON-LD."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def _extract_images(soup: BeautifulSoup, html: str, json_ld: dict[str, Any]) -> list[str]:
    """Collect all product image URLs from JSON-LD and page markup."""
    images: list[str] = []

    json_image = json_ld.get("image")
    if isinstance(json_image, str):
        images.append(json_image)
    elif isinstance(json_image, list):
        images.extend(url for url in json_image if isinstance(url, str))

    for match in IMAGE_PATTERN.findall(html):
        images.append(match.split("?")[0])

    for img in soup.select("img[src], img[data-src]"):
        src = img.get("src") or img.get("data-src")
        if src and "images.olx.com.pk" in src:
            images.append(urljoin(BASE_URL, src).split("?")[0])

    deduped: list[str] = []
    seen: set[str] = set()
    for url in images:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _extract_seller(json_ld: dict[str, Any], soup: BeautifulSoup) -> str | None:
    """Resolve seller name from JSON-LD offers or profile link text."""
    offers = json_ld.get("offers")
    if isinstance(offers, list) and offers:
        seller = offers[0].get("seller")
        if isinstance(seller, str) and seller.strip():
            return seller.strip()
    elif isinstance(offers, dict):
        seller = offers.get("seller")
        if isinstance(seller, str) and seller.strip():
            return seller.strip()

    profile = soup.select_one("a[href*='/profile/']")
    if profile:
        text = profile.get_text(strip=True)
        if text:
            return text
    return None


def _extract_rating(soup: BeautifulSoup) -> float | None:
    """OLX classified listings rarely expose ratings; return NULL when absent."""
    rating_el = soup.select_one("[data-aut-id='itemRating'], [class*='rating']")
    if not rating_el:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text(strip=True))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def parse_product(url: str, session: requests.Session | None = None) -> dict[str, Any] | None:
    """
    Fetch and parse a single OLX product detail page.
    Throttling is applied inside fetch_html before the network request.
    """
    try:
        html = fetch_html(url, session=session)
    except requests.RequestException as exc:
        logger.warning("Failed to fetch product %s: %s", url, exc)
        return None

    soup = BeautifulSoup(html, "lxml")
    json_ld = _extract_json_ld_product(soup)

    product_id = extract_product_id(url, soup)
    if not product_id:
        logger.warning("Could not determine product_id for %s", url)
        return None

    name = None
    if json_ld.get("name"):
        name = str(json_ld["name"]).strip()
    else:
        title_el = soup.select_one("h1")
        if title_el:
            name = title_el.get_text(strip=True)

    if not name:
        logger.warning("Missing product name for %s", url)
        return None

    price = None
    offers = json_ld.get("offers")
    if isinstance(offers, list) and offers:
        price = _parse_price(offers[0].get("price"))
    elif isinstance(offers, dict):
        price = _parse_price(offers.get("price"))

    if price is None:
        price_el = soup.select_one("[data-aut-id='itemPrice']")
        if price_el:
            price = _parse_price(price_el.get_text(strip=True))

    description = None
    if json_ld.get("description"):
        description = str(json_ld["description"]).strip()
    else:
        desc_el = soup.select_one(
            "[data-aut-id='itemDescriptionContent'], [data-aut-id='itemDescription']"
        )
        if desc_el:
            description = desc_el.get_text(" ", strip=True)

    seller_name = _extract_seller(json_ld, soup)
    rating = _extract_rating(soup)
    image_urls = _extract_images(soup, html, json_ld)

    return {
        "product_id": product_id,
        "name": name,
        "price": price,
        "description": description,
        "seller_name": seller_name,
        "rating": rating,
        "source_url": url.split("?")[0],
        "image_urls": image_urls,
    }

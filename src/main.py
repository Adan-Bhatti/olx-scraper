"""Entry point: concurrent OLX scraper scheduler with progress tracking."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from db import get_image_count, get_product_count, init_db, save_product
from parser import parse_product
from scraper import build_search_url, fetch_html, get_next_page, get_product_urls

TARGET_PRODUCT_COUNT = 1000
MAX_WORKERS = 8
DEFAULT_KEYWORD = "smartphones"

visited_urls: set[str] = set()
visited_lock = threading.Lock()

stats = {
    "pages_crawled": 0,
    "products_saved": 0,
    "errors_skipped": 0,
    "futures_submitted": 0,
}
stats_lock = threading.Lock()


def configure_logging(log_file: Path | None = None) -> None:
    """Send logs to console and optionally to Execution_Log.txt."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def mark_visited(url: str) -> bool:
    """Atomically mark a URL as visited. Returns False if already seen."""
    with visited_lock:
        if url in visited_urls:
            return False
        visited_urls.add(url)
        return True


def worker(product_url: str, session: requests.Session) -> bool:
    """Fetch, parse, and persist a single product detail page."""
    if not mark_visited(product_url):
        return False

    product = parse_product(product_url, session=session)
    if not product:
        with stats_lock:
            stats["errors_skipped"] += 1
        return False

    inserted = save_product(product)
    with stats_lock:
        if inserted:
            stats["products_saved"] += 1
    return inserted


def crawl(
    keyword: str = DEFAULT_KEYWORD,
    target_count: int = TARGET_PRODUCT_COUNT,
    max_workers: int = MAX_WORKERS,
) -> None:
    """Traverse search pages and scrape product details concurrently."""
    init_db()
    logger = logging.getLogger(__name__)
    start_time = time.perf_counter()

    page_url: str | None = build_search_url(keyword)
    session = requests.Session()

    logger.info(
        "Starting OLX Pakistan scraper | keyword=%r | target=%d | workers=%d (ThreadPoolExecutor)",
        keyword,
        target_count,
        max_workers,
    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        pending: set = set()

        while page_url and get_product_count() < target_count:
            if not mark_visited(page_url):
                logger.info("Search page already visited, stopping pagination: %s", page_url)
                break

            try:
                html = fetch_html(page_url, session=session)
            except requests.RequestException as exc:
                logger.warning("Search page fetch failed %s: %s", page_url, exc)
                with stats_lock:
                    stats["errors_skipped"] += 1
                break

            product_urls = get_product_urls(page_url, session=session, html=html)
            next_page_url = get_next_page(page_url, html=html, session=session)

            with stats_lock:
                stats["pages_crawled"] += 1

            new_urls = [url for url in product_urls if url not in visited_urls]
            logger.info(
                "Page crawled: %s | found=%d | new=%d | saved=%d/%d",
                page_url,
                len(product_urls),
                len(new_urls),
                get_product_count(),
                target_count,
            )

            for url in new_urls:
                if get_product_count() >= target_count:
                    break
                future = pool.submit(worker, url, session)
                pending.add(future)
                with stats_lock:
                    stats["futures_submitted"] += 1

            done = {f for f in pending if f.done()}
            for future in done:
                pending.discard(future)
                try:
                    future.result()
                except requests.RequestException as exc:
                    logger.warning("Worker request error: %s", exc)
                    with stats_lock:
                        stats["errors_skipped"] += 1
                except Exception as exc:
                    logger.warning("Worker unexpected error: %s", exc)
                    with stats_lock:
                        stats["errors_skipped"] += 1

            if get_product_count() >= target_count:
                logger.info("Target of %d products reached.", target_count)
                break

            if not product_urls:
                logger.info("No products on page, stopping: %s", page_url)
                break

            if next_page_url and next_page_url != page_url:
                page_url = next_page_url
            else:
                logger.info("No further pagination available after %s", page_url)
                break

        logger.info("Waiting for remaining worker tasks (%d pending)...", len(pending))
        for future in as_completed(pending):
            try:
                future.result()
            except requests.RequestException as exc:
                logger.warning("Worker request error: %s", exc)
                with stats_lock:
                    stats["errors_skipped"] += 1
            except Exception as exc:
                logger.warning("Worker unexpected error: %s", exc)
                with stats_lock:
                    stats["errors_skipped"] += 1

            if get_product_count() >= target_count:
                continue

    elapsed = time.perf_counter() - start_time
    product_count = get_product_count()
    image_count = get_image_count()

    logger.info("=" * 60)
    logger.info("SCRAPE COMPLETE")
    logger.info("Concurrency: ThreadPoolExecutor with %d workers", max_workers)
    logger.info("Pages crawled: %d", stats["pages_crawled"])
    logger.info("Detail tasks submitted: %d", stats["futures_submitted"])
    logger.info("Products saved (this run): %d", stats["products_saved"])
    logger.info("Errors skipped: %d", stats["errors_skipped"])
    logger.info("Visited URLs (session): %d", len(visited_urls))
    logger.info("Final DB counts -> products: %d | product_images: %d", product_count, image_count)
    logger.info("Elapsed time: %.1f seconds (%.1f minutes)", elapsed, elapsed / 60)
    logger.info("=" * 60)

    if product_count < target_count:
        logger.warning(
            "Target not reached: %d/%d products in database.",
            product_count,
            target_count,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OLX Pakistan concurrent web scraper")
    parser.add_argument(
        "--keyword",
        default=DEFAULT_KEYWORD,
        help="Search keyword (default: smartphones)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=TARGET_PRODUCT_COUNT,
        help="Minimum products to collect (default: 1000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help="ThreadPoolExecutor worker count (default: 8)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent
    configure_logging(project_root / "Execution_Log.txt")
    crawl(keyword=args.keyword, target_count=args.target, max_workers=args.workers)

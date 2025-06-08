import os
import json
import re
from datetime import datetime
from urllib.parse import urlparse
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://tds.s-anand.net/#/2025-01/"
BASE_ORIGIN = "https://tds.s-anand.net"
OUTPUT_FILE = "tds_minimal_content.json"

visited = set()
course_pages = []

def extract_all_internal_links(page):
    try:
        links = page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
        return [link for link in links if link.startswith(BASE_ORIGIN) and '/#/' in link]
    except Exception:
        return []

def wait_for_main_content(page):
    try:
        page.wait_for_selector("article.markdown-section#main", timeout=10000)
        return page.inner_html("article.markdown-section#main")
    except PlaywrightTimeoutError:
        return None

def clean_title(title):
    return title.split(" - ")[0].strip() if " - " in title else title.strip()

def crawl_page(page, url):
    if url in visited:
        return
    visited.add(url)

    print(f"🧭 Visiting: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"⚠️ Error loading {url}: {e}")
        return

    html = wait_for_main_content(page)
    if not html:
        return

    title = clean_title(page.title())
    markdown = md(html)

    course_pages.append({
        "title": title,
        "url": url,
        "markdown": markdown
    })

    for link in extract_all_internal_links(page):
        if link not in visited:
            crawl_page(page, link)

def main():
    os.makedirs("tmp", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        crawl_page(page, BASE_URL)
        browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(course_pages, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done. {len(course_pages)} pages saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

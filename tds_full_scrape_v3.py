import os
import json
from datetime import datetime
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://tds.s-anand.net/#/2025-01/"
BASE_ORIGIN = "https://tds.s-anand.net"
OUTPUT_FILE = "tds_rich_content.json"

visited = set()
scraped = []

def get_internal_links(page):
    try:
        return list(set(
            link for link in page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
            if link.startswith(BASE_ORIGIN) and '/#/' in link
        ))
    except:
        return []

def extract_html(page):
    try:
        page.wait_for_selector("article.markdown-section#main", timeout=10000)
        return page.inner_html("article.markdown-section#main")
    except PlaywrightTimeoutError:
        return None

def extract_text(page):
    try:
        return page.eval_on_selector("article.markdown-section#main", "el => el.innerText")
    except:
        return ""

def extract_headings_links_images(page):
    try:
        headings = page.eval_on_selector_all("article h1, article h2, article h3", "els => els.map(el => el.innerText)")
        links = page.eval_on_selector_all("article a[href]", "els => els.map(el => ({ text: el.innerText, href: el.href }))")
        images = page.eval_on_selector_all("article img", "els => els.map(el => ({ alt: el.alt, src: el.src }))")
        return headings, links, images
    except:
        return [], [], []

def extract_metadata(page):
    # Example: meta description or other page meta info if present
    try:
        description = page.eval_on_selector("meta[name='description']", "el => el.content") or ""
        author = page.eval_on_selector("meta[name='author']", "el => el.content") or ""
        return {"description": description, "author": author}
    except:
        return {}

def crawl(page, url):
    if url in visited:
        return
    visited.add(url)

    print(f"🔍 Visiting: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)  # wait for JS to fully render content
    except Exception as e:
        print(f"⚠️ Error loading {url}: {e}")
        return

    html = extract_html(page)
    if not html:
        print(f"⚠️ Skipping {url} — no main content")
        return

    text_content = extract_text(page)
    title = page.title().split(" - ")[0].strip() or f"Page {len(visited)}"
    markdown = md(html)
    headings, links, images = extract_headings_links_images(page)
    meta = extract_metadata(page)

    scraped.append({
        "title": title,
        "url": url,
        "downloaded_at": datetime.now().isoformat(),
        "markdown": markdown,
        "text": text_content,
        "headings": headings,
        "links": links,
        "images": images,
        "metadata": meta
    })

    for link in get_internal_links(page):
        crawl(page, link)

def main():
    os.makedirs("tmp", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        crawl(page, BASE_URL)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Done. {len(scraped)} pages saved to {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    main()

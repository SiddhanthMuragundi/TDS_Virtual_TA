import os
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://tds.s-anand.net/#/2025-01/"
BASE_ORIGIN = "https://tds.s-anand.net"
OUTPUT_DIR = "markdown_files"
METADATA_FILE = "metadata.json"

visited = set()
metadata = []

def sanitize_filename(title):
    # Replace forbidden filename characters and trim spaces, also replace spaces with underscores
    return re.sub(r'[\/*?:"<>|]', "_", title).strip().replace(" ", "_")

def extract_all_internal_links(page):
    try:
        links = page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
    except Exception as e:
        print(f"⚠️ Error extracting links: {e}")
        return []

    # Only keep internal links that have the base origin and contain '/#/'
    filtered = set()
    for link in links:
        if link.startswith(BASE_ORIGIN) and '/#/' in link:
            filtered.add(link)
    return list(filtered)

def wait_for_article_and_get_html(page):
    try:
        page.wait_for_selector("article.markdown-section#main", timeout=10000)
        return page.inner_html("article.markdown-section#main")
    except PlaywrightTimeoutError:
        print("⚠️ Timeout waiting for main article content")
        return None

def save_markdown_file(title, url, html):
    filename = sanitize_filename(title)
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.md")
    
    markdown = md(html)

    # Write YAML frontmatter and markdown content
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: \"{title}\"\n")
        f.write(f"original_url: \"{url}\"\n")
        f.write(f"downloaded_at: \"{datetime.now().isoformat()}\"\n")
        f.write("---\n\n")
        f.write(markdown)

    return filename

def crawl_page(page, url):
    if url in visited:
        return
    visited.add(url)

    print(f"📄 Visiting: {url}")

    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)  # wait for JS to render
    except Exception as e:
        print(f"❌ Error loading page {url}: {e}")
        return

    html = wait_for_article_and_get_html(page)
    if not html:
        print(f"⚠️ Skipping {url} due to no content")
        return

    # Extract title safely
    title = page.title()
    if title and " - " in title:
        title = title.split(" - ")[0].strip()
    if not title:
        title = f"page_{len(visited)}"

    filename = save_markdown_file(title, url, html)

    metadata.append({
        "title": title,
        "filename": filename + ".md",
        "original_url": url,
        "downloaded_at": datetime.now().isoformat()
    })

    # Crawl links recursively
    links = extract_all_internal_links(page)
    for link in links:
        if link not in visited:
            crawl_page(page, link)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    global visited, metadata

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        crawl_page(page, BASE_URL)

        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        print(f"✅ Completed. {len(metadata)} pages saved.")

        browser.close()

if __name__ == "__main__":
    main()

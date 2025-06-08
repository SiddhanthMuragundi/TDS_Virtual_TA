import os
import json
import csv
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright, TimeoutError

# === CONFIG ===
BASE_URL = "https://discourse.onlinedegree.iitm.ac.in"
CATEGORY_ID = 34
CATEGORY_JSON_URL = f"{BASE_URL}/c/courses/tds-kb/{CATEGORY_ID}.json"
AUTH_STATE_FILE = "auth.json"
DATE_FROM = datetime(2025, 1, 1)
DATE_TO = datetime(2025, 4, 14)

KEYWORDS = ["GA", "quiz", "deadline", "OpenAI", "API", "token", "error"]

# === HELPERS ===
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")

def extract_tags(text):
    return [kw for kw in KEYWORDS if kw.lower() in text.lower()]

def classify_post(text):
    if "?" in text and len(text) < 300:
        return "question"
    elif "thanks" in text.lower() or "resolved" in text.lower():
        return "gratitude"
    elif len(text) > 600:
        return "explanation"
    return "other"

def hash_post(text):
    return hashlib.sha256(text.encode()).hexdigest()

# === AUTH ===
def login_and_save_auth(playwright):
    print("🔐 No auth found. Launching browser for manual login...")
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{BASE_URL}/login")
    print("🌐 Please log in manually using Google. Then press ▶️ (Resume) in Playwright bar.")
    page.pause()
    context.storage_state(path=AUTH_STATE_FILE)
    print("✅ Login state saved.")
    browser.close()

def is_authenticated(page):
    try:
        page.goto(CATEGORY_JSON_URL, timeout=10000)
        page.wait_for_selector("pre", timeout=5000)
        json.loads(page.inner_text("pre"))
        return True
    except (TimeoutError, json.JSONDecodeError):
        return False

# === SCRAPER ===
def scrape_posts(playwright):
    print("🔍 Starting scrape using saved session...")
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=AUTH_STATE_FILE)
    page = context.new_page()

    all_topics = []
    page_num = 0
    while True:
        paginated_url = f"{CATEGORY_JSON_URL}?page={page_num}"
        print(f"📦 Fetching page {page_num}...")
        page.goto(paginated_url)

        try:
            data = json.loads(page.inner_text("pre"))
        except:
            data = json.loads(page.content())

        topics = data.get("topic_list", {}).get("topics", [])
        if not topics:
            break

        all_topics.extend(topics)
        page_num += 1

    print(f"📄 Found {len(all_topics)} total topics across all pages")

    filtered_posts = []
    for topic in all_topics:
        created_at = parse_date(topic["created_at"])
        if DATE_FROM <= created_at <= DATE_TO:
            topic_url = f"{BASE_URL}/t/{topic['slug']}/{topic['id']}.json"
            page.goto(topic_url)

            try:
                topic_data = json.loads(page.inner_text("pre"))
            except:
                topic_data = json.loads(page.content())

            posts = topic_data.get("post_stream", {}).get("posts", [])
            accepted_answer_id = topic_data.get("accepted_answer", topic_data.get("accepted_answer_post_id"))

            reply_counter = {}
            for post in posts:
                reply_to = post.get("reply_to_post_number")
                if reply_to is not None:
                    reply_counter[reply_to] = reply_counter.get(reply_to, 0) + 1

            # Topic summary (top 3 liked posts)
            top_posts = sorted(posts, key=lambda x: x.get("like_count", 0), reverse=True)[:3]
            topic_summary = " ".join(BeautifulSoup(p["cooked"], "html.parser").get_text() for p in top_posts)

            for post in posts:
                post_text = BeautifulSoup(post["cooked"], "html.parser").get_text()
                filtered_posts.append({
                    "topic_id": topic["id"],
                    "topic_title": topic.get("title"),
                    "summary_text": topic_summary,
                    "category_id": topic.get("category_id"),
                    "tags": topic.get("tags", []),
                    "post_id": post["id"],
                    "post_number": post["post_number"],
                    "author": post["username"],
                    "created_at": post["created_at"],
                    "updated_at": post.get("updated_at"),
                    "reply_to_post_number": post.get("reply_to_post_number"),
                    "is_reply": post.get("reply_to_post_number") is not None,
                    "reply_count": reply_counter.get(post["post_number"], 0),
                    "like_count": post.get("like_count", 0),
                    "is_accepted_answer": post["id"] == accepted_answer_id,
                    "mentioned_users": [u["username"] for u in post.get("mentioned_users", [])],
                    "url": f"{BASE_URL}/t/{topic['slug']}/{topic['id']}/{post['post_number']}",
                    "content": post_text,
                    "markdown": md(post["cooked"]),
                    "hash": hash_post(post_text),
                    "type": classify_post(post_text),
                    "auto_tags": extract_tags(post_text),
                    "popularity_score": post.get("like_count", 0) + reply_counter.get(post["post_number"], 0)
                })

    with open("discourse_posts.json", "w") as f:
        json.dump(filtered_posts, f, indent=2)

    # with open("discourse_posts.csv", "w", newline="") as f:
    #     writer = csv.DictWriter(f, fieldnames=filtered_posts[0].keys())
    #     writer.writeheader()
    #     writer.writerows(filtered_posts)

    with open("discourse_posts.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=filtered_posts[0].keys())
        writer.writeheader()
        writer.writerows(filtered_posts)


    print(f"✅ Scraped {len(filtered_posts)} posts between {DATE_FROM.date()} and {DATE_TO.date()}")
    browser.close()

# === MAIN ===
def main():
    with sync_playwright() as p:
        if not os.path.exists(AUTH_STATE_FILE):
            login_and_save_auth(p)
        else:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=AUTH_STATE_FILE)
            page = context.new_page()
            if not is_authenticated(page):
                print("⚠️ Session invalid. Re-authenticating...")
                browser.close()
                login_and_save_auth(p)
            else:
                print("✅ Using existing authenticated session.")
                browser.close()

        scrape_posts(p)

if __name__ == "__main__":
    main()

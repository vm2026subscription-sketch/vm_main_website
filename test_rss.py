import urllib.request
import urllib.error

urls = [
    "https://www.jagranjosh.com/rss/education-news",
    "https://www.jagranjosh.com/rss/education",
    "https://www.jagran.com/rss/education.xml",
    "https://news.careers360.com/rss",
    "https://news.careers360.com/rss/education-news",
    "https://news.careers360.com/feed",
    "https://www.shiksha.com/news/rss",
    "https://www.shiksha.com/rss/news",
    "https://www.shiksha.com/news/feed",
    "https://admission.aglasem.com/feed",
    "https://www.hindustantimes.com/feeds/rss/education/rssfeed.xml",
    "https://www.indiatoday.in/rss/1206577",
    "https://timesofindia.indiatimes.com/rssfeeds/913168846.cms"
]

header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

print(f"{'URL':<70} | {'Status':<7} | {'RSS/XML'}")
print("-" * 90)

for url in urls:
    req = urllib.request.Request(url, headers=header)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.getcode()
            content = response.read(500).decode('utf-8', errors='ignore').strip().lower()
            is_xml = "<?xml" in content or "<rss" in content or "<feed" in content
            print(f"{url:<70} | {status:<7} | {'Yes' if is_xml else 'No'}")
    except urllib.error.HTTPError as e:
        print(f"{url:<70} | {e.code:<7} | Error")
    except Exception as e:
        print(f"{url:<70} | {'Err':<7} | {str(e)[:20]}")

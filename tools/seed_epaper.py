#!/usr/bin/env python
"""Seed sample epaper data with multiple languages and articles."""
import json
import os
from datetime import datetime, timedelta

# Load existing editions
data_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'epaper_editions.json')

with open(data_file, 'r', encoding='utf-8') as f:
    editions = json.load(f)

# Check if we already have a Marathi edition
has_marathi = any(e['language'] == 'Marathi' for e in editions)

if not has_marathi:
    # Create a Marathi edition from yesterday
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    
    marathi_edition = {
        "date": yesterday,
        "name": "दैनिक संस्करण",
        "language": "Marathi",
        "published": True,
        "masthead_image_url": "",
        "footer_links": [],
        "header_items": [],
        "created_at": datetime.now().isoformat(),
        "pages": [
            {
                "page_number": 1,
                "category": "मुख पृष्ठ",
                "image_path": "",
                "page_image_url": "",
                "layout_json": [],
                "blocks": [
                    {
                        "id": 101,
                        "article_id": 101,
                        "headline": "महाराष्ट्र बोर्ड परीक्षा परिणाम जाहीर",
                        "title": "महाराष्ट्र बोर्ड परीक्षा परिणाम जाहीर",
                        "sub_headline": "10 वीं आणि 12 वीं मार्कशीट डाउनलोड करा",
                        "body_text": "महाराष्ट्र स्टेट बोर्ड ऑफ सेकेंडरी आणि हायर सेकेंडरी एजुकेशनने 10वी आणि 12वी परीक्षेचे परिणाम घोषित केले. विद्यार्थी त्यांच्या रोल नंबरने महाराष्ट्रबोर्ड.इन वेबसाइटवर परिणाम तपासू शकतात.",
                        "body_html": "<p>महाराष्ट्र स्टेट बोर्ड परीक्षा परिणाम घोषित</p>",
                        "author": "विद्यार्थी मित्र डेस्क",
                        "category_label": "शिक्षा",
                        "category": "शिक्षा",
                        "image_url": "",
                        "image": "",
                        "gallery": [],
                        "x": 0, "y": 0, "w": 400, "h": 300,
                        "width": 400, "height": 300,
                        "border_width": 0,
                        "border_radius": 0,
                        "border_color": "#e41e26",
                        "border_style": "solid"
                    },
                    {
                        "id": 102,
                        "article_id": 102,
                        "headline": "UPSC परीक्षा तयारीची सल्ले",
                        "title": "UPSC परीक्षा तयारीची सल्ले",
                        "sub_headline": "सदरचा काळ एक सेमिस्टरचा आहे",
                        "body_text": "UPSC सिव्हिल सर्व्हिसेज परीक्षेत यशस्वी होण्यासाठी नियमित अभ्यास आणि योग्य रणनीती आवश्यक आहे.",
                        "body_html": "<p>UPSC परीक्षेची तयारी कशी करावी</p>",
                        "author": "विद्यार्थी मित्र डेस्क",
                        "category_label": "करियर",
                        "category": "करियर",
                        "image_url": "",
                        "image": "",
                        "gallery": [],
                        "x": 420, "y": 0, "w": 380, "h": 300,
                        "width": 380, "height": 300,
                        "border_width": 0,
                        "border_radius": 0,
                        "border_color": "#e41e26",
                        "border_style": "solid"
                    }
                ],
                "articles": []
            }
        ]
    }
    
    editions.append(marathi_edition)
    
    # Save back to file
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(editions, f, ensure_ascii=False, indent=2)
    
    print("✓ Marathi edition added successfully")
    print(f"  Date: {yesterday}")
    print(f"  Name: दैनिक संस्करण")
    print(f"  Language: Marathi")
else:
    print("✓ Marathi edition already exists")

# Print summary
print("\nEditions summary:")
for e in editions:
    print(f"  {e['date']} - {e['language']} (Published: {e.get('published', True)})")

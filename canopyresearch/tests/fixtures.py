"""
Shared test fixtures and sample data for canopyresearch tests.

Provider response data used across provider and ingestion tests.
"""

# Minimal RSS 2.0 feed with 2 items
RSS_MINIMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Item 1</title>
      <link>https://example.com/1</link>
      <description>Summary 1</description>
      <pubDate>Mon, 17 Feb 2025 12:00:00 GMT</pubDate>
      <guid>guid-1</guid>
    </item>
    <item>
      <title>Item 2</title>
      <link>https://example.com/2</link>
      <description>Summary 2</description>
      <pubDate>Tue, 18 Feb 2025 12:00:00 GMT</pubDate>
      <guid>guid-2</guid>
    </item>
  </channel>
</rss>
"""

# Algolia HN Search API response with 2 hits
ALGOLIA_RESPONSE = {
    "hits": [
        {
            "objectID": "123",
            "story_id": "123",
            "title": "Test Story",
            "url": "https://example.com/article",
            "author": "user1",
            "points": 42,
            "num_comments": 5,
            "created_at_i": 1700000000,
        },
        {
            "objectID": "124",
            "story_id": "124",
            "title": "Ask HN",
            "url": None,
            "author": "user2",
            "points": 10,
            "num_comments": 3,
            "created_at_i": 1700000100,
        },
    ]
}

# Reddit listing JSON response with 1 post
REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "Test Post",
                    "selftext": "Post body",
                    "url": "https://example.com/link",
                    "permalink": "/r/python/comments/abc123/test/",
                    "author": "testuser",
                    "subreddit": "python",
                    "score": 10,
                    "created_utc": 1700000000,
                }
            }
        ]
    }
}

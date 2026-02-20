# HackerNews Source Configuration Guide

This guide explains how to configure HackerNews sources to reduce noise and improve signal quality.

## Basic Configuration

```json
{
  "listing": "front_page",
  "limit": 50,
  "fetch_full_article": true
}
```

## Filtering Options

To reduce noise and improve signal quality, use these filtering options:

### Filter by Engagement (Recommended)

Filter stories by minimum points and/or comments to focus on higher-quality content:

```json
{
  "listing": "front_page",
  "limit": 50,
  "min_points": 50,
  "min_comments": 10,
  "fetch_full_article": true
}
```

**Options:**
- `min_points`: Minimum upvotes (e.g., `50` = only stories with 50+ points)
- `min_comments`: Minimum comments (e.g., `10` = only stories with 10+ comments)

**When to use:**
- You're seeing too much noise from low-engagement stories
- You want to focus on discussions and popular content
- Your research domain benefits from community validation

**Example configurations:**

**High-quality only (strict filtering):**
```json
{
  "listing": "front_page",
  "limit": 30,
  "min_points": 100,
  "min_comments": 20,
  "fetch_full_article": true
}
```

**Moderate filtering (balanced):**
```json
{
  "listing": "front_page",
  "limit": 50,
  "min_points": 30,
  "min_comments": 5,
  "fetch_full_article": true
}
```

**Light filtering (more content):**
```json
{
  "listing": "front_page",
  "limit": 50,
  "min_points": 10,
  "fetch_full_article": true
}
```

### Keyword Search

Filter stories by keywords in title or URL:

```json
{
  "listing": "front_page",
  "limit": 50,
  "query": "machine learning",
  "fetch_full_article": true
}
```

**When to use:**
- You want to focus on specific topics
- Your research domain has clear keywords
- You want to reduce off-topic content

**Example:**
```json
{
  "listing": "front_page",
  "limit": 50,
  "query": "AI research",
  "min_points": 20,
  "fetch_full_article": true
}
```

### Post-Fetch Filtering

For additional client-side filtering after Algolia fetch:

```json
{
  "listing": "front_page",
  "limit": 50,
  "min_points": 30,
  "min_points_post_fetch": 50,
  "min_comments_post_fetch": 15,
  "fetch_full_article": true
}
```

**Options:**
- `min_points_post_fetch`: Additional points threshold applied after fetch
- `min_comments_post_fetch`: Additional comments threshold applied after fetch

**When to use:**
- You want double-filtering (Algolia + client-side)
- You need stricter filtering than Algolia provides
- You want to filter based on metadata that's only available after fetch

## Listing Types

- `"front_page"` (default): Top stories on HackerNews front page
- `"new"`: Newest stories
- `"ask_hn"`: Ask HN posts
- `"show_hn"`: Show HN posts

## Complete Example

**High-quality research-focused configuration:**
```json
{
  "listing": "front_page",
  "limit": 30,
  "min_points": 50,
  "min_comments": 10,
  "query": "research",
  "fetch_full_article": true
}
```

This configuration will:
1. Fetch top 30 stories from front page
2. Filter to only stories with 50+ points
3. Filter to only stories with 10+ comments
4. Filter to only stories containing "research" in title/URL
5. Extract full article content

## Tips for Reducing Noise

1. **Start strict, then relax**: Begin with high thresholds (`min_points: 100`) and lower them if you're missing important content
2. **Combine filters**: Use both `min_points` and `min_comments` for better signal
3. **Use keywords wisely**: Broad keywords may miss relevant content; specific keywords reduce noise but may miss related topics
4. **Monitor results**: Check your document list to see if filtering is working as expected
5. **Adjust per workspace**: Different research domains may need different thresholds

## Troubleshooting

**Problem: Too few documents**
- Lower `min_points` and `min_comments` thresholds
- Remove or broaden `query` keyword
- Increase `limit`

**Problem: Still too much noise**
- Increase `min_points` and `min_comments` thresholds
- Add more specific `query` keywords
- Consider using `min_points_post_fetch` for additional filtering
- Consider switching to cloud embeddings for better semantic understanding

**Problem: Missing relevant content**
- Lower thresholds
- Remove keyword filters
- Check if stories are being filtered out by post-fetch filters

## Related Documentation

- [Embedding Model Selection](./embeddings.md) - For improving semantic understanding
- [Source Management](../canopyresearch/templates/canopyresearch/source_form.html) - UI for configuring sources

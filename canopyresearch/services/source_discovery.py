"""
Source discovery service for finding relevant sources based on workspace search terms.
"""

import logging
from collections import Counter

from canopyresearch.models import (
    Document,
    Source,
    Workspace,
    WorkspaceCoreFeedback,
    WorkspaceSearchTerms,
)
from canopyresearch.services.providers import (
    HackerNewsProvider,
    RSSProvider,
    SubredditProvider,
)
from canopyresearch.services.term_extraction import (
    extract_terms_from_document,
    extract_terms_from_text,
    extract_terms_with_llm,
)

logger = logging.getLogger(__name__)

# Term weights by source
TERM_WEIGHTS = {
    "name": 2.0,
    "description": 1.5,
    "document": 1.0,
    "manual": 2.0,
}


def initialize_workspace_search_terms(workspace: Workspace, use_llm: bool = True) -> None:
    """
    Extract initial search terms from workspace name and description.

    Uses LLM-based extraction by default for better semantic understanding.
    Called when workspace is created or updated.

    Args:
        workspace: Workspace to initialize terms for
        use_llm: Whether to use LLM extraction (default: True)
    """
    # Extract from workspace name
    if workspace.name:
        if use_llm:
            try:
                name_terms = extract_terms_with_llm(workspace.name, context="workspace name")
            except Exception as e:
                logger.debug("LLM extraction failed for workspace name, using simple: %s", e)
                name_terms = extract_terms_from_text(workspace.name)
        else:
            name_terms = extract_terms_from_text(workspace.name)

        for term in name_terms:
            WorkspaceSearchTerms.objects.update_or_create(
                workspace=workspace,
                term=term,
                defaults={
                    "source": "name",
                    "weight": TERM_WEIGHTS["name"],
                },
            )

    # Extract from workspace description
    if workspace.description:
        if use_llm:
            try:
                desc_terms = extract_terms_with_llm(
                    workspace.description, context="workspace description"
                )
            except Exception as e:
                logger.debug("LLM extraction failed for workspace description, using simple: %s", e)
                desc_terms = extract_terms_from_text(workspace.description)
        else:
            desc_terms = extract_terms_from_text(workspace.description)

        for term in desc_terms:
            WorkspaceSearchTerms.objects.update_or_create(
                workspace=workspace,
                term=term,
                defaults={
                    "source": "description",
                    "weight": TERM_WEIGHTS["description"],
                },
            )


def extract_search_terms(workspace: Workspace) -> list[str]:
    """
    Extract search terms from workspace context.

    Combines terms from:
    - Workspace name
    - Workspace description
    - Thumbs-up documents
    - Existing WorkspaceSearchTerms records

    Returns deduplicated, weighted list of terms.

    Args:
        workspace: Workspace to extract terms for

    Returns:
        List of search terms (ordered by weight, highest first)
    """
    term_weights: Counter[str] = Counter()

    # Extract from workspace name
    if workspace.name:
        name_terms = extract_terms_from_text(workspace.name)
        for term in name_terms:
            term_weights[term] += TERM_WEIGHTS["name"]

    # Extract from workspace description
    if workspace.description:
        desc_terms = extract_terms_from_text(workspace.description)
        for term in desc_terms:
            term_weights[term] += TERM_WEIGHTS["description"]

    # Extract from thumbs-up documents
    thumbs_up_feedback = WorkspaceCoreFeedback.objects.filter(
        workspace=workspace, vote="up"
    ).select_related("document")

    for feedback in thumbs_up_feedback:
        doc_terms = extract_terms_from_document(feedback.document)
        for term in doc_terms:
            term_weights[term] += TERM_WEIGHTS["document"]

    # Add existing search terms
    existing_terms = WorkspaceSearchTerms.objects.filter(workspace=workspace)
    for term_obj in existing_terms:
        term_weights[term_obj.term] += term_obj.weight

    # Sort by weight (descending) and return terms
    sorted_terms = sorted(term_weights.items(), key=lambda x: x[1], reverse=True)
    return [term for term, _ in sorted_terms]


def update_search_terms_from_feedback(
    workspace: Workspace, document: Document, use_llm: bool = True
) -> None:
    """
    Extract terms from a thumbs-up document and add to search terms.

    Uses LLM-based extraction by default for better semantic understanding.
    Called when user gives positive feedback on a document.

    Args:
        workspace: Workspace context
        document: Document that received thumbs-up
        use_llm: Whether to use LLM extraction (default: True)
    """
    terms = extract_terms_from_document(document, use_llm=use_llm)
    weight = TERM_WEIGHTS["document"]

    for term in terms:
        WorkspaceSearchTerms.objects.update_or_create(
            workspace=workspace,
            term=term,
            defaults={
                "source": "document",
                "weight": weight,
                "document": document,
            },
        )

    logger.info(
        "Updated search terms from feedback: %d terms from document %s", len(terms), document.id
    )


def discover_source_candidates(
    workspace: Workspace, provider_type: str, limit_per_provider: int = 20
) -> list[dict]:
    """
    Discover source candidates for a workspace.

    Args:
        workspace: Workspace to discover sources for
        provider_type: "hackernews", "subreddit", or "rss"
        limit_per_provider: Max results per provider search

    Returns:
        List of candidate dicts with:
        - provider_type
        - name (suggested source name)
        - config (provider config dict)
        - sample_documents (preview of what would be ingested)
        - match_reason (why this was suggested)
    """
    terms = extract_search_terms(workspace)
    if not terms:
        return []

    query = " ".join(terms[:10])  # Use top 10 terms for search
    candidates: list[dict] = []

    if provider_type == "hackernews":
        try:
            # Fetch a sample of matching stories to show as a preview.
            # We suggest a single HN source configured to search for these terms.
            sample_docs = HackerNewsProvider.search(terms, limit=5)
            candidates.append(
                {
                    "provider_type": "hackernews",
                    "name": f"HN: {query[:60]}",
                    "config": {
                        "query": query,
                        "listing": "search",
                        "limit": 50,
                        "min_points": 10,
                        "fetch_full_article": True,
                    },
                    "sample_documents": [
                        {
                            "title": doc.get("title", ""),
                            "url": doc.get("url", ""),
                            "points": doc.get("points", 0),
                            "comments": doc.get("num_comments", 0),
                        }
                        for doc in sample_docs
                    ],
                    "match_reason": f"Hacker News stories matching: {', '.join(terms[:5])}",
                }
            )
        except Exception as e:
            logger.exception("Failed to search HackerNews: %s", e)

    elif provider_type == "subreddit":
        try:
            # Search for subreddits by name/description — not posts.
            # This avoids r/anime appearing because one post mentioned "coding".
            subreddit_results = SubredditProvider.search_subreddits(terms, limit=limit_per_provider)
            for sr in subreddit_results:
                candidates.append(
                    {
                        "provider_type": "subreddit",
                        "name": f"r/{sr['name']}",
                        "config": {
                            "subreddit": sr["name"],
                            "listing": "hot",
                            "limit": 100,
                            "fetch_full_article": True,
                        },
                        "sample_documents": [],
                        "match_reason": sr["description"] or sr["title"],
                        "subscriber_count": sr["subscriber_count"],
                    }
                )
        except Exception as e:
            logger.exception("Failed to search Reddit: %s", e)

    elif provider_type == "rss":
        try:
            # Use LLM to discover RSS feeds
            api_key = None  # Will use env var
            feed_results = RSSProvider.search(terms, limit=limit_per_provider, api_key=api_key)

            for feed_info in feed_results:
                candidates.append(
                    {
                        "provider_type": "rss",
                        "name": feed_info.get("title", feed_info.get("feed_url", "")),
                        "config": {
                            "url": feed_info.get("feed_url", ""),
                            "fetch_full_article": True,
                        },
                        "sample_documents": feed_info.get("sample_entries", []),
                        "match_reason": feed_info.get("description", f"RSS feed for: {query}"),
                    }
                )
        except Exception as e:
            logger.exception("Failed to discover RSS feeds: %s", e)

    return candidates


def create_source_from_candidate(
    workspace: Workspace, candidate: dict, name: str | None = None
) -> Source:
    """
    Create a Source from a discovery candidate.

    Pre-populates config with search terms used.

    Args:
        workspace: Workspace to create source for
        candidate: Candidate dict from discover_source_candidates()
        name: Optional custom name (uses candidate name if not provided)

    Returns:
        Created Source instance
    """
    source_name = name or candidate.get("name", "New Source")
    provider_type = candidate.get("provider_type")
    config = candidate.get("config", {}).copy()

    # Ensure source name is unique
    base_name = source_name
    counter = 1
    while workspace.sources.filter(name=source_name).exists():
        source_name = f"{base_name} ({counter})"
        counter += 1

    source = Source.objects.create(
        workspace=workspace,
        name=source_name,
        provider_type=provider_type,
        config=config,
        status="healthy",
    )

    logger.info("Created source %s from candidate for workspace %s", source.id, workspace.id)
    return source


def auto_discover_and_create_sources(
    workspace: Workspace,
    max_sources_per_provider: int = 3,
    provider_types: list[str] | None = None,
) -> dict[str, int]:
    """
    Automatically discover and create sources for a workspace.

    Discovers candidates for each provider type and automatically creates
    sources from the top candidates. This is intended to be called when a
    workspace is first created to populate it with relevant sources.

    Args:
        workspace: Workspace to discover sources for
        max_sources_per_provider: Maximum number of sources to create per provider type (default: 3)
        provider_types: List of provider types to discover (default: all available)

    Returns:
        Dict with counts of sources created per provider type:
        {
            "hackernews": 2,
            "subreddit": 3,
            "rss": 1,
            "total": 6
        }
    """
    if provider_types is None:
        provider_types = ["hackernews", "subreddit", "rss"]

    created_counts: dict[str, int] = {}
    total_created = 0

    for provider_type in provider_types:
        try:
            # Discover candidates for this provider type
            candidates = discover_source_candidates(
                workspace, provider_type, limit_per_provider=max_sources_per_provider * 2
            )

            # Create sources from top candidates
            created = 0
            for candidate in candidates[:max_sources_per_provider]:
                try:
                    create_source_from_candidate(workspace, candidate)
                    created += 1
                    total_created += 1
                except Exception as e:
                    logger.exception(
                        "Failed to create source from candidate for %s: %s", provider_type, e
                    )

            created_counts[provider_type] = created
            logger.info(
                "Auto-discovered %d sources for %s provider in workspace %s",
                created,
                provider_type,
                workspace.id,
            )
        except Exception as e:
            logger.exception(
                "Failed to discover sources for provider %s in workspace %s: %s",
                provider_type,
                workspace.id,
                e,
            )
            created_counts[provider_type] = 0

    created_counts["total"] = total_created
    logger.info("Auto-discovered %d total sources for workspace %s", total_created, workspace.id)
    return created_counts

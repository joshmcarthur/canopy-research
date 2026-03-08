"""
Document summarization service for canopyresearch.

Generates workspace-contextual summaries using an OpenAI-compatible chat API.
Falls back gracefully (returns "") when no API key is configured or the call fails.
"""

import logging
import os

logger = logging.getLogger(__name__)


def summarize_document(document) -> str:
    """
    Generate a workspace-contextual summary for a document.

    Uses OPENAI_API_KEY, OPENAI_API_BASE, and TERM_EXTRACTION_MODEL env vars.
    Returns "" if LLM is unavailable or the call fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set, skipping summarization for document %s", document.id)
        return ""

    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed, skipping summarization")
        return ""

    try:
        workspace = document.workspace
        search_terms = list(
            workspace.search_terms.order_by("-weight").values_list("term", flat=True)[:10]
        )
        key_topics = ", ".join(search_terms) if search_terms else "(none)"

        prompt = (
            f'You are a research assistant helping analyse content for a workspace called "{workspace.name}".\n\n'
            f"Workspace description: {workspace.description or '(none)'}\n"
            f"Key topics: {key_topics}\n\n"
            f"Summarise the following article in 2-4 sentences. "
            f"Focus on aspects relevant to the workspace topics. "
            f"Be specific and informative — avoid vague generalisations.\n\n"
            f"Title: {document.title}\n"
            f"Content: {document.content[:3000]}\n\n"
            f"Return only the summary text, no preamble."
        )

        api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        model_name = os.environ.get("TERM_EXTRACTION_MODEL", "gpt-4o-mini")

        client = openai.OpenAI(api_key=api_key, base_url=api_base)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful research assistant. Return only the summary text.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        logger.warning("Summarization failed for document %s: %s", document.id, e)
        return ""

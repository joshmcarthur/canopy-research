"""Pytest configuration for canopyresearch."""

import pytest

from canopyresearch.tests.fixtures import (
    ALGOLIA_RESPONSE,
    REDDIT_RESPONSE,
    RSS_MINIMAL,
)


@pytest.fixture(autouse=True)
def _use_immediate_task_backend(settings):
    """Use ImmediateBackend for tests so tasks run synchronously without a worker."""
    settings.TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        }
    }


# Provider test data fixtures (for tests that prefer dependency injection)
@pytest.fixture
def rss_minimal():
    """Minimal RSS 2.0 feed with 2 items."""
    return RSS_MINIMAL


@pytest.fixture
def algolia_response():
    """Algolia HN Search API response with 2 hits."""
    return ALGOLIA_RESPONSE


@pytest.fixture
def reddit_response():
    """Reddit listing JSON response with 1 post."""
    return REDDIT_RESPONSE

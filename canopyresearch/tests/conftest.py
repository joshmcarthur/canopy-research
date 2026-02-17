"""
Pytest configuration and fixtures for browser tests.

This module provides:
- Stable test fixtures for creating test data
- Browser fixtures using pytest-playwright
- Live server fixture integration with Django

Note on DJANGO_ALLOW_ASYNC_UNSAFE:
Playwright's sync API internally uses an async event loop (via greenlets).
Django's ORM detects this and raises SynchronousOnlyOperation. While setting
DJANGO_ALLOW_ASYNC_UNSAFE=true is a common workaround, the proper solution
is to ensure all database operations happen in fixtures BEFORE the page
fixture creates the async context. However, due to pytest-playwright's
architecture, the flag is often necessary and is considered acceptable
for test environments where transactions provide isolation.
"""

import os

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from canopyresearch.models import Source, Workspace

# Allow Django ORM operations in async contexts created by Playwright.
# This is necessary because Playwright's sync API uses greenlets which
# create an async event loop that Django detects. While not ideal, this
# is a pragmatic solution commonly used in the Django + Playwright community.
# It's safe for tests because:
# 1. Tests run in isolated database transactions
# 2. The flag only affects the test process, not production
# 3. All database operations happen in fixtures before page navigation
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

User = get_user_model()


# ============================================================================
# Stable Test Data Fixtures (The "World")
# ============================================================================


@pytest.fixture
def test_user(db):
    """Create a test user for authentication."""
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def test_user_client(db, test_user):
    """Create a Django test client authenticated as test_user."""
    client = Client()
    client.login(username="testuser", password="testpass")
    return client


@pytest.fixture
def workspace(db, admin_user):
    """Create a test workspace owned by admin_user (for browser tests)."""
    return Workspace.objects.create(
        name="Test Workspace",
        description="A test workspace for browser testing",
        owner=admin_user,
    )


@pytest.fixture
def workspace_with_sources(db, admin_user):
    """Create a workspace with multiple sources for testing."""
    workspace = Workspace.objects.create(
        name="Workspace with Sources",
        description="A workspace with pre-populated sources",
        owner=admin_user,
    )
    Source.objects.create(
        workspace=workspace,
        name="RSS Feed",
        provider_type="rss",
        config={"url": "https://example.com/feed.xml"},
        status="healthy",
    )
    Source.objects.create(
        workspace=workspace,
        name="Hacker News",
        provider_type="hackernews",
        config={},
        status="healthy",
    )
    return workspace


@pytest.fixture
def multiple_workspaces(db, admin_user):
    """Create multiple workspaces for testing workspace switching."""
    workspaces = []
    for i in range(3):
        workspace = Workspace.objects.create(
            name=f"Workspace {i + 1}",
            description=f"Description for workspace {i + 1}",
            owner=admin_user,
        )
        workspaces.append(workspace)
    return workspaces


# ============================================================================
# Browser Test Fixtures
# ============================================================================


@pytest.fixture
def admin_user(db):
    """Create admin user for AutoLoginMiddleware."""
    return User.objects.create_user(
        username="admin",
        email="admin@example.com",
        password="admin",
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def authenticated_page(live_server, page, admin_user, db):
    """
    Provide an authenticated Playwright page.

    This fixture:
    1. Ensures admin_user is created (via fixture dependency, BEFORE page creation)
    2. Starts Django's live test server (via live_server fixture)
    3. Creates a Playwright browser page (this creates async context)
    4. AutoLoginMiddleware automatically authenticates as admin user
    5. Returns the authenticated page ready for testing

    Fixture ordering ensures database operations happen before async context:
    - `db` fixture ensures database access
    - `admin_user` fixture creates user synchronously
    - `live_server` starts server in background thread
    - `page` fixture creates Playwright page (async context starts here)
    - Navigation happens after all sync operations complete

    Each test gets a fresh page with a clean database state (thanks to
    Django's transactional test database).
    """
    # All database operations (admin_user creation) happen BEFORE this point
    # because fixtures are resolved in dependency order. The `page` fixture
    # creates the async context, but by then all sync DB operations are done.

    # AutoLoginMiddleware will automatically log in as admin
    # Just navigate to any page to trigger authentication
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    # Set base URL for easier navigation
    page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
    return page


@pytest.fixture
def authenticated_page_with_workspace(authenticated_page, live_server, workspace):
    """
    Provide an authenticated page with a workspace already created.

    Navigates to the workspace detail page and returns the page.
    """
    authenticated_page.goto(f"{live_server.url}/workspaces/{workspace.id}/")
    authenticated_page.wait_for_load_state("networkidle")
    return authenticated_page


# ============================================================================
# Helper Functions
# ============================================================================


def create_workspace_via_api(client, name="Test Workspace", description=""):
    """Helper to create a workspace via Django test client."""
    response = client.post(
        "/",
        {"name": name, "description": description},
        follow=True,
    )
    return response


def create_source_via_api(
    client, workspace_id, name="Test Source", provider_type="rss", config=None
):
    """Helper to create a source via Django test client."""
    if config is None:
        config = {"url": "https://example.com/feed.xml"}
    response = client.post(
        f"/workspaces/{workspace_id}/sources/create/",
        {
            "name": name,
            "provider_type": provider_type,
            "config_json": str(config).replace("'", '"'),
            "status": "healthy",
        },
        follow=True,
    )
    return response

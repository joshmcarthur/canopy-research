"""
Browser tests for workspace management workflows.

Tests the following user flows:
1. Creating a workspace
2. Viewing workspace list with cards
3. Switching between workspaces (HTMX)
4. Navigating to workspace detail
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.django_db, pytest.mark.browser]


@pytest.mark.django_db
class TestWorkspaceCreation:
    """Test workspace creation workflow."""

    def test_create_workspace_from_homepage(self, authenticated_page, live_server):
        """Test creating a workspace from the root page."""
        page = authenticated_page

        # Navigate to homepage
        page.goto(f"{live_server.url}/")
        page.wait_for_load_state("networkidle")

        # Verify we see the workspace creation form
        prompt = page.locator("h2.canopy-prompt")
        expect(prompt).to_contain_text("What can I help you with?")

        # Fill in workspace form (only name field exists)
        name_input = page.locator('sl-input[name="name"]')
        expect(name_input).to_be_visible()
        name_input.fill("My Research Workspace")

        # Submit the form (button with "Create workspace" text)
        submit_button = page.locator('sl-button[type="submit"]:has-text("Create workspace")')
        expect(submit_button).to_be_visible()
        submit_button.click()

        # Wait for redirect to workspace detail page
        page.wait_for_url(f"{live_server.url}/workspaces/*/")
        page.wait_for_load_state("networkidle")

        # Verify workspace name appears on detail page
        workspace_name = page.locator("h2")
        expect(workspace_name).to_contain_text("My Research Workspace")

    def test_workspace_list_shows_created_workspaces(
        self, authenticated_page, live_server, multiple_workspaces
    ):
        """Test that workspace list displays all workspaces."""
        page = authenticated_page

        # Navigate to homepage
        page.goto(f"{live_server.url}/")
        page.wait_for_load_state("networkidle")

        # Verify "Your workspaces" section exists
        section_header = page.locator("h3")
        expect(section_header).to_contain_text("Your workspaces")

        # Verify all workspaces are displayed as cards
        workspace_cards = page.locator("sl-card")
        expect(workspace_cards).to_have_count(3)

        # Verify workspace names appear in cards (in the header slot)
        for idx, workspace_item in enumerate(multiple_workspaces):
            card = workspace_cards.nth(idx)
            expect(card.locator('[slot="header"] strong')).to_contain_text(workspace_item.name)

    def test_workspace_card_shows_source_and_document_counts(
        self, authenticated_page, live_server, workspace_with_sources
    ):
        """Test that workspace cards show source and document counts."""
        page = authenticated_page

        # Navigate to homepage
        page.goto(f"{live_server.url}/")
        page.wait_for_load_state("networkidle")

        # Find the workspace card
        workspace_card = page.locator("sl-card").filter(has_text=workspace_with_sources.name)
        expect(workspace_card).to_be_visible()

        # Verify badges show source and document counts (in footer slot)
        footer = workspace_card.locator('[slot="footer"]')
        badges = footer.locator("sl-badge")
        expect(badges.first).to_contain_text("2 sources")
        expect(badges.nth(1)).to_contain_text("0 documents")


@pytest.mark.django_db
class TestWorkspaceNavigation:
    """Test workspace navigation and detail views."""

    def test_navigate_to_workspace_detail(self, authenticated_page, live_server, workspace):
        """Test clicking 'View' button navigates to workspace detail."""
        page = authenticated_page

        # Navigate to homepage
        page.goto(f"{live_server.url}/")
        page.wait_for_load_state("networkidle")

        # Find and click the View button for our workspace
        view_button = page.locator('sl-button:has-text("View")').first
        view_button.click()

        # Wait for navigation to workspace detail
        page.wait_for_url(f"{live_server.url}/workspaces/{workspace.id}/*")
        page.wait_for_load_state("networkidle")

        # Verify workspace name appears
        workspace_name = page.locator("h2")
        expect(workspace_name).to_contain_text(workspace.name)

    def test_workspace_detail_shows_tabs(self, authenticated_page_with_workspace, workspace):
        """Test that workspace detail page shows Sources and Documents tabs."""
        page = authenticated_page_with_workspace

        # Verify tabs are present
        sources_tab = page.locator('a.tab-link:has-text("Sources")')
        documents_tab = page.locator('a.tab-link:has-text("Documents")')

        expect(sources_tab).to_be_visible()
        expect(documents_tab).to_be_visible()

        # Verify Sources tab is active by default
        expect(sources_tab).to_have_class("active")

    def test_switch_between_tabs(self, authenticated_page_with_workspace, workspace, live_server):
        """Test switching between Sources and Documents tabs using HTMX."""
        page = authenticated_page_with_workspace

        # Click Documents tab
        documents_tab = page.locator('a.tab-link:has-text("Documents")')
        documents_tab.click()

        # Wait for HTMX swap
        page.wait_for_load_state("networkidle")

        # Verify Documents tab is now active
        expect(documents_tab).to_have_class("active")

        # Verify Sources tab is no longer active
        sources_tab = page.locator('a.tab-link:has-text("Sources")')
        expect(sources_tab).not_to_have_class("active")

        # Click back to Sources tab
        sources_tab.click()
        page.wait_for_load_state("networkidle")

        # Verify Sources tab is active again
        expect(sources_tab).to_have_class("active")


@pytest.mark.django_db
class TestWorkspaceSwitcher:
    """Test workspace switcher dropdown (HTMX)."""

    def test_workspace_switcher_dropdown(
        self, authenticated_page_with_workspace, multiple_workspaces, live_server
    ):
        """Test that workspace switcher dropdown shows all workspaces."""
        page = authenticated_page_with_workspace

        # Find workspace switcher dropdown (in header)
        switcher = page.locator("#workspace-switcher")
        expect(switcher).to_be_visible()

        # Open dropdown by clicking trigger button
        trigger = switcher.locator("button.workspace-switcher-trigger")
        expect(trigger).to_be_visible()
        trigger.click()
        page.wait_for_timeout(500)  # Wait for dropdown animation

        # Verify all workspaces appear in dropdown menu
        menu = switcher.locator("sl-menu")
        expect(menu).to_be_visible()

        # Check that menu items exist for each workspace
        menu_items = menu.locator("sl-menu-item")
        # Should have multiple_workspaces (3) + workspace from authenticated_page_with_workspace (1) + "New workspace" (1) = 5 items
        # But workspace might be the same, so at least 4 items
        assert menu_items.count() >= 4, f"Expected at least 4 menu items, got {menu_items.count()}"

        # Verify workspace names appear for multiple_workspaces
        for ws in multiple_workspaces:
            expect(menu.locator(f'sl-menu-item[value="{ws.id}"]')).to_contain_text(ws.name)

        # Verify "New workspace" option exists
        expect(menu.locator('sl-menu-item[value="new"]')).to_contain_text("New workspace")

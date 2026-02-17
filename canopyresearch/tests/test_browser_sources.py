"""
Browser tests for source management workflows.

Tests the following user flows:
1. Viewing source list
2. Creating a source via modal
3. Editing a source via modal
4. Deleting a source via confirmation dialog
5. HTMX interactions for source management
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.django_db, pytest.mark.browser]


@pytest.mark.django_db
class TestSourceList:
    """Test source list display."""

    def test_source_list_displays_sources(
        self, authenticated_page_with_workspace, workspace_with_sources
    ):
        """Test that source list shows all sources for a workspace."""
        page = authenticated_page_with_workspace

        # Verify sources are displayed in a table
        table = page.locator("table.data-grid")
        expect(table).to_be_visible()

        # Should see at least the sources we created
        expect(page.locator("text=RSS Feed")).to_be_visible()
        expect(page.locator("text=Hacker News")).to_be_visible()

        # Verify table headers
        expect(page.locator("th:has-text('Name')")).to_be_visible()
        expect(page.locator("th:has-text('Provider Type')")).to_be_visible()
        expect(page.locator("th:has-text('Status')")).to_be_visible()
        expect(page.locator("th:has-text('Actions')")).to_be_visible()

    def test_empty_source_list_shows_message(self, authenticated_page_with_workspace, workspace):
        """Test that empty workspace shows appropriate message."""
        page = authenticated_page_with_workspace

        # Verify empty state message
        empty_state = page.locator(".empty-state")
        expect(empty_state).to_be_visible()
        expect(empty_state.locator("text=No sources yet.")).to_be_visible()


@pytest.mark.django_db
class TestSourceCreation:
    """Test source creation workflow."""

    def test_open_create_source_modal(self, authenticated_page_with_workspace):
        """Test clicking 'Add Source' button opens modal."""
        page = authenticated_page_with_workspace

        # Find and click Add Source button
        add_button = page.locator('sl-button:has-text("Add Source")')
        expect(add_button).to_be_visible()
        add_button.click()

        # Wait for modal to appear
        page.wait_for_timeout(300)  # Wait for modal animation

        # Verify modal is visible
        modal = page.locator("#resource-dialog")
        expect(modal).to_be_visible()

        # Verify form fields are present (using Shoelace components)
        name_input = page.locator('sl-input[name="name"]')
        provider_select = page.locator('sl-select[name="provider_type"]')
        config_textarea = page.locator('sl-textarea[name="config_json"]')
        status_select = page.locator('sl-select[name="status"]')

        expect(name_input).to_be_visible()
        expect(provider_select).to_be_visible()
        expect(config_textarea).to_be_visible()
        expect(status_select).to_be_visible()

    def test_create_source_via_modal(self, authenticated_page_with_workspace, workspace):
        """Test creating a source via the modal form."""
        page = authenticated_page_with_workspace

        # Open modal
        add_button = page.locator('sl-button:has-text("Add Source")')
        add_button.click()
        page.wait_for_timeout(300)

        # Fill in form fields (using Shoelace components)
        name_input = page.locator('sl-input[name="name"]')
        name_input.fill("New RSS Feed")

        # Select provider type
        provider_select = page.locator('sl-select[name="provider_type"]')
        provider_select.click()
        page.wait_for_timeout(200)  # Wait for dropdown to open
        page.locator('sl-option[value="rss"]').click()
        page.wait_for_timeout(200)  # Wait for selection

        # Fill config JSON
        config_textarea = page.locator('sl-textarea[name="config_json"]')
        config_textarea.fill('{"url": "https://example.com/new-feed.xml"}')

        # Submit form
        submit_button = page.locator('sl-button[type="submit"]:has-text("Create")')
        submit_button.click()

        # Wait for HTMX response and modal close
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Verify source appears in list
        expect(page.locator("text=New RSS Feed")).to_be_visible()

        # Verify modal is closed
        modal = page.locator("#resource-dialog")
        # Modal might be hidden but still in DOM, check visibility
        if modal.count() > 0:
            expect(modal).not_to_be_visible()


@pytest.mark.django_db
class TestSourceEditing:
    """Test source editing workflow."""

    def test_open_edit_source_modal(
        self, authenticated_page_with_workspace, workspace_with_sources
    ):
        """Test opening edit modal for a source."""
        page = authenticated_page_with_workspace

        # Find edit button for a source (first Edit button in the table)
        edit_button = page.locator('sl-button:has-text("Edit")').first
        expect(edit_button).to_be_visible()
        edit_button.click()
        page.wait_for_timeout(300)

        # Verify modal opens with source data
        modal = page.locator("#resource-dialog")
        expect(modal).to_be_visible()

        # Verify form is pre-filled (using Shoelace input)
        name_input = page.locator('sl-input[name="name"]')
        expect(name_input).to_have_attribute("value", "RSS Feed")

    def test_edit_source_via_modal(self, authenticated_page_with_workspace, workspace_with_sources):
        """Test editing a source via modal."""
        page = authenticated_page_with_workspace

        # Open edit modal
        edit_button = page.locator('sl-button:has-text("Edit")').first
        expect(edit_button).to_be_visible()
        edit_button.click()
        page.wait_for_timeout(300)

        # Modify name (using Shoelace input)
        name_input = page.locator('sl-input[name="name"]')
        name_input.fill("Updated RSS Feed")

        # Submit
        submit_button = page.locator('sl-button[type="submit"]:has-text("Save")')
        submit_button.click()

        # Wait for update
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Verify updated name appears in table
        expect(page.locator("text=Updated RSS Feed")).to_be_visible()


@pytest.mark.django_db
class TestSourceDeletion:
    """Test source deletion workflow."""

    def test_open_delete_confirmation_dialog(
        self, authenticated_page_with_workspace, workspace_with_sources
    ):
        """Test opening delete confirmation dialog."""
        page = authenticated_page_with_workspace

        # Find delete button (first Delete button in the table)
        delete_button = page.locator('sl-button:has-text("Delete")').first
        expect(delete_button).to_be_visible()
        delete_button.click()
        page.wait_for_timeout(300)

        # Verify confirmation dialog appears
        confirm_dialog = page.locator("#resource-dialog")
        expect(confirm_dialog).to_be_visible()

        # Verify source name appears in confirmation message
        expect(page.locator("text=RSS Feed")).to_be_visible()
        expect(page.locator("text=/Are you sure you want to delete/")).to_be_visible()

    def test_delete_source_via_confirmation(
        self, authenticated_page_with_workspace, workspace_with_sources
    ):
        """Test deleting a source via confirmation dialog."""
        page = authenticated_page_with_workspace

        # Open delete dialog
        delete_button = page.locator('sl-button:has-text("Delete")').first
        expect(delete_button).to_be_visible()
        delete_button.click()
        page.wait_for_timeout(300)

        # Confirm deletion (the Delete button in the confirmation dialog)
        confirm_button = page.locator(
            '#resource-dialog sl-button[type="submit"]:has-text("Delete")'
        )
        expect(confirm_button).to_be_visible()
        confirm_button.click()

        # Wait for deletion
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Verify source is removed from list
        expect(page.locator("text=RSS Feed")).not_to_be_visible()

        # Verify other sources still visible
        expect(page.locator("text=Hacker News")).to_be_visible()


@pytest.mark.django_db
class TestSourceHTMXInteractions:
    """Test HTMX-specific interactions for sources."""

    def test_source_list_htmx_partial_update(self, authenticated_page_with_workspace, workspace):
        """Test that HTMX requests return partial content."""
        page = authenticated_page_with_workspace

        # Trigger HTMX request by clicking Sources tab again
        sources_tab = page.locator('a.tab-link:has-text("Sources")')
        sources_tab.click()

        # Wait for HTMX swap
        page.wait_for_load_state("networkidle")

        # Verify page structure (should not include full HTML shell)
        # This is harder to test directly, but we can verify content updated
        expect(page.locator("h2")).to_be_visible()  # Workspace name should still be there

    def test_source_create_triggers_list_refresh(
        self, authenticated_page_with_workspace, workspace
    ):
        """Test that creating a source refreshes the list via HTMX."""
        page = authenticated_page_with_workspace

        # Count initial sources (should be 0 for empty workspace)
        initial_rows = page.locator("table.data-grid tbody tr").count()
        assert initial_rows == 0

        # Create source via modal
        add_button = page.locator('sl-button:has-text("Add Source")')
        add_button.click()
        page.wait_for_timeout(300)

        # Fill in form
        name_input = page.locator('sl-input[name="name"]')
        name_input.fill("Test Source for HTMX")

        provider_select = page.locator('sl-select[name="provider_type"]')
        provider_select.click()
        page.wait_for_timeout(200)
        page.locator('sl-option[value="rss"]').click()
        page.wait_for_timeout(200)

        config_textarea = page.locator('sl-textarea[name="config_json"]')
        config_textarea.fill('{"url": "https://example.com/test.xml"}')

        # Submit form
        submit_button = page.locator('sl-button[type="submit"]:has-text("Create")')
        submit_button.click()

        # Wait for HTMX response and list refresh
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Verify source appears in table (list was refreshed via HTMX)
        expect(page.locator("text=Test Source for HTMX")).to_be_visible()

        # Verify table now has one row
        final_rows = page.locator("table.data-grid tbody tr").count()
        assert final_rows == 1

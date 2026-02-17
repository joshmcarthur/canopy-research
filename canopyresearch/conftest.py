"""Pytest configuration for canopyresearch."""

import pytest


@pytest.fixture(autouse=True)
def _use_immediate_task_backend(settings):
    """Use ImmediateBackend for tests so tasks run synchronously without a worker."""
    settings.TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        }
    }

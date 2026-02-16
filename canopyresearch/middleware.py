"""
Django middleware for auto-authentication.
"""

from django.contrib.auth import get_user_model, login


class AutoLoginMiddleware:
    """Middleware that automatically authenticates a superuser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Process request and auto-authenticate if needed."""
        if not request.user.is_authenticated:
            User = get_user_model()
            user = User.objects.get(username="admin")
            login(request, user)

        return self.get_response(request)

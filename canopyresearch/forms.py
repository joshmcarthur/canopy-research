"""
Django forms for canopyresearch.
"""

import json

from django import forms
from django.core.exceptions import ValidationError

from canopyresearch.models import Source, Workspace


class WorkspaceForm(forms.ModelForm):
    """Form for creating/editing workspaces."""

    class Meta:
        model = Workspace
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class SourceForm(forms.ModelForm):
    """Form for creating/editing sources."""

    config_json = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        required=False,
        help_text='JSON configuration (e.g., {"url": "https://example.com/feed.xml"})',
    )

    class Meta:
        model = Source
        fields = ["name", "provider_type", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "provider_type": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        """Initialize form with workspace context."""
        super().__init__(*args, **kwargs)
        if workspace:
            self.instance.workspace = workspace

        # Initialize config_json from instance config
        if self.instance and self.instance.pk and self.instance.config:
            self.fields["config_json"].initial = json.dumps(self.instance.config, indent=2)
        else:
            self.fields["config_json"].initial = "{}"

    def clean_config_json(self):
        """Validate and parse JSON config."""
        config_json = self.cleaned_data.get("config_json", "{}")
        try:
            return json.loads(config_json)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

    def save(self, commit=True):
        """Save form with parsed JSON config."""
        instance = super().save(commit=False)
        instance.config = self.cleaned_data["config_json"]
        if commit:
            instance.save()
        return instance

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('canopyresearch', '0006_document_scoring_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkspaceSearchTerms',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('term', models.CharField(db_index=True, max_length=200)),
                ('source', models.CharField(choices=[('name', 'Workspace name'), ('description', 'Workspace description'), ('document', 'Extracted from document'), ('manual', 'Manually added')], max_length=50)),
                ('weight', models.FloatField(default=1.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(blank=True, help_text="Document this term was extracted from (if source='document')", null=True, on_delete=django.db.models.deletion.SET_NULL, to='canopyresearch.document')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_terms', to='canopyresearch.workspace')),
            ],
            options={
                'ordering': ['-weight', 'term'],
            },
        ),
        migrations.AddIndex(
            model_name='workspacesearchterms',
            index=models.Index(fields=['workspace', '-weight'], name='canopyresea_workspace_idx'),
        ),
        migrations.AddIndex(
            model_name='workspacesearchterms',
            index=models.Index(fields=['workspace', 'source'], name='canopyresea_source_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='workspacesearchterms',
            unique_together={('workspace', 'term')},
        ),
    ]

# Generated migration to refactor Document-Source relationship to many-to-many

from django.db import migrations, models
import django.db.models.deletion


def migrate_document_sources(apps, schema_editor):
    """Migrate existing Document.source FK relationships to DocumentSource join table."""
    Document = apps.get_model('canopyresearch', 'Document')
    DocumentSource = apps.get_model('canopyresearch', 'DocumentSource')
    
    # Migrate all existing document-source relationships
    for document in Document.objects.all():
        if document.source_id:  # Only if source exists (should always be true, but be safe)
            DocumentSource.objects.get_or_create(
                document=document,
                source_id=document.source_id,
            )


def reverse_migrate_document_sources(apps, schema_editor):
    """Reverse migration: set Document.source to first DocumentSource.source."""
    Document = apps.get_model('canopyresearch', 'Document')
    DocumentSource = apps.get_model('canopyresearch', 'DocumentSource')
    
    # For each document, set source to the first associated source
    for document in Document.objects.all():
        doc_source = DocumentSource.objects.filter(document=document).first()
        if doc_source:
            document.source_id = doc_source.source_id
            document.save()


class Migration(migrations.Migration):

    dependencies = [
        ('canopyresearch', '0001_initial'),
    ]

    operations = [
        # Step 1: Create DocumentSource join model
        migrations.CreateModel(
            name='DocumentSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discovered_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_sources', to='canopyresearch.document')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_sources', to='canopyresearch.source')),
            ],
        ),
        migrations.AddConstraint(
            model_name='documentsource',
            constraint=models.UniqueConstraint(fields=('document', 'source'), name='canopyresearch_documentsource_unique_document_source'),
        ),
        migrations.AddIndex(
            model_name='documentsource',
            index=models.Index(fields=['source', '-discovered_at'], name='canopyresea_source__discovered_at_idx'),
        ),
        
        # Step 2: Migrate existing data
        migrations.RunPython(migrate_document_sources, reverse_migrate_document_sources),
        
        # Step 3: Remove old constraint and index that includes source
        migrations.RemoveConstraint(
            model_name='document',
            name='unique_doc_hash_per_workspace',
        ),
        migrations.RemoveIndex(
            model_name='document',
            name='canopyresea_workspa_8dd499_idx',  # Index on (workspace, source, -published_at)
        ),
        
        # Step 4: Remove source FK from Document
        migrations.RemoveField(
            model_name='document',
            name='source',
        ),
        
        # Step 5: Add many-to-many relationship
        migrations.AddField(
            model_name='document',
            name='sources',
            field=models.ManyToManyField(related_name='documents', through='canopyresearch.DocumentSource', to='canopyresearch.source'),
        ),
        
        # Step 6: Add new unique constraint (workspace, hash)
        migrations.AddConstraint(
            model_name='document',
            constraint=models.UniqueConstraint(
                condition=models.Q(('hash__gt', '')),
                fields=('workspace', 'hash'),
                name='unique_doc_hash_per_workspace',
            ),
        ),
    ]

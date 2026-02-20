from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('canopyresearch', '0005_cluster_metrics'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='alignment',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='velocity',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='novelty',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='relevance',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='scored_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='source',
            name='weight',
            field=models.FloatField(default=1.0),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['workspace', '-relevance'], name='canopyresea_doc_relevance_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['workspace', '-alignment'], name='canopyresea_doc_alignment_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['workspace', '-velocity'], name='canopyresea_doc_velocity_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['workspace', '-novelty'], name='canopyresea_doc_novelty_idx'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('canopyresearch', '0004_embeddings_and_clusters'),
    ]

    operations = [
        migrations.AddField(
            model_name='cluster',
            name='alignment',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cluster',
            name='velocity',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cluster',
            name='previous_centroid',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='cluster',
            name='drift_distance',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cluster',
            name='metrics_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='cluster',
            index=models.Index(fields=['workspace', 'alignment'], name='canopyresea_workspa_alignment_idx'),
        ),
        migrations.AddIndex(
            model_name='cluster',
            index=models.Index(fields=['workspace', 'velocity'], name='canopyresea_workspa_velocity_idx'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("canopyresearch", "0011_add_cluster_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="summary",
            field=models.TextField(blank=True, default=""),
        ),
    ]

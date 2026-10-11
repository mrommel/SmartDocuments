from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_alter_document_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="find_addresses",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="DocumentAddress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("address", models.CharField(max_length=255)),
                ("category", models.CharField(choices=[("customer", "Customer"), ("shop", "Shop"), ("private", "Private"), ("business", "Business"), ("other", "Other")], default="other", max_length=12)),
                ("geocode_result", models.JSONField(blank=True, null=True)),
                ("geocode_error", models.CharField(blank=True, max_length=255)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="addresses", to="documents.document")),
            ],
            options={"ordering": ["pk"]},
        ),
    ]

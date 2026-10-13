from django.db import migrations


def add_profile_field_controls(apps, schema_editor):
    Configuration = apps.get_model(
        "registrations", "RegistrationFieldConfiguration"
    )
    database = schema_editor.connection.alias
    roles = [
        "FARMER",
        "WHOLESALER",
        "RETAILER",
        "USER_ADMIN",
        "FINANCIAL_MANAGER",
        "SUPER_ADMIN",
    ]

    Configuration.objects.using(database).update_or_create(
        field_key="full_name",
        stage="PROFILE",
        defaults={
            "label": "Full name",
            "description": "Your name as it appears on official documents.",
            "required": True,
            "visible": True,
            "display_order": 1,
            "roles": roles,
            "options": [],
            "editable_after_approval": True,
        },
    )
    for field_key, display_order in (("phone", 5), ("location", 6)):
        Configuration.objects.using(database).filter(
            field_key=field_key, stage="PROFILE"
        ).update(
            roles=roles if field_key == "phone" else ["FARMER", "WHOLESALER", "RETAILER"],
            editable_after_approval=True,
            display_order=display_order,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0004_registrationfieldconfiguration"),
    ]

    operations = [
        migrations.RunPython(add_profile_field_controls, migrations.RunPython.noop),
    ]

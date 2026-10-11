from django.db import migrations


def add_registration_products(apps, schema_editor):
    ProductType = apps.get_model("registrations", "AgriculturalProductType")
    database = schema_editor.connection.alias
    products = [
        ("cabbage", "Cabbage", "Vegetables"),
        ("garlic", "Garlic", "Vegetables"),
        ("lettuce", "Lettuce", "Vegetables"),
        ("cucumber", "Cucumber", "Vegetables"),
        ("beetroot", "Beetroot", "Vegetables"),
        ("banana", "Banana", "Fruits"),
        ("orange", "Orange", "Fruits"),
        ("apple", "Apple", "Fruits"),
        ("avocado", "Avocado", "Fruits"),
        ("papaya", "Papaya", "Fruits"),
        ("lemon", "Lemon", "Fruits"),
        ("watermelon", "Watermelon", "Fruits"),
        ("pineapple", "Pineapple", "Fruits"),
        ("grapes", "Grapes", "Fruits"),
    ]
    for code, name, category in products:
        ProductType.objects.using(database).get_or_create(
            category=category,
            name=name,
            defaults={"code": code, "active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("registrations", "0002_administrativelocationimport_and_more")]

    operations = [
        migrations.RunPython(add_registration_products, migrations.RunPython.noop),
    ]

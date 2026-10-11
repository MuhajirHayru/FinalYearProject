import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from registrations.models import AdministrativeLocation, LocationLevel


class Command(BaseCommand):
    help = (
        "Import verified administrative locations from CSV columns "
        "source_id,name,level,parent_source_id."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            with open(options["csv_path"], encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
        except OSError as exc:
            raise CommandError(f"Cannot read location dataset: {exc}") from exc

        required = {"source_id", "name", "level", "parent_source_id"}
        if not rows or not required.issubset(rows[0]):
            raise CommandError(
                "CSV must contain source_id,name,level,parent_source_id columns "
                "and at least one data row."
            )

        normalized = {}
        allowed_levels = {level.value for level in LocationLevel}
        for line, row in enumerate(rows, start=2):
            source_id = row["source_id"].strip()
            name = row["name"].strip()
            level = row["level"].strip().upper()
            parent_source_id = row["parent_source_id"].strip()
            if not source_id or not name or level not in allowed_levels:
                raise CommandError(f"Invalid source_id, name, or level on CSV line {line}.")
            if source_id in normalized:
                raise CommandError(f"Duplicate source_id {source_id!r} on CSV line {line}.")
            normalized[source_id] = {
                "name": name,
                "level": level,
                "parent_source_id": parent_source_id,
                "line": line,
            }

        existing = {
            item.source_id: item
            for item in AdministrativeLocation.objects.select_related("parent")
        }
        all_levels = {key: value["level"] for key, value in normalized.items()}
        all_levels.update({key: value.level for key, value in existing.items()})

        for source_id, item in normalized.items():
            parent_id = item["parent_source_id"]
            if parent_id and parent_id not in all_levels:
                raise CommandError(
                    f"Unknown parent_source_id {parent_id!r} on CSV line {item['line']}."
                )
            if parent_id and all_levels[parent_id] == item["level"]:
                raise CommandError(
                    f"Parent and child have the same level on CSV line {item['line']}."
                )

        for source_id in normalized:
            seen = set()
            current = source_id
            while current in normalized:
                if current in seen:
                    raise CommandError(f"Location hierarchy contains a cycle at {current!r}.")
                seen.add(current)
                current = normalized[current]["parent_source_id"]

        resolved = dict(existing)
        created_count = 0
        updated_count = 0
        pending = set(normalized)
        while pending:
            ready = [
                source_id
                for source_id in pending
                if not normalized[source_id]["parent_source_id"]
                or normalized[source_id]["parent_source_id"] in resolved
            ]
            if not ready:
                raise CommandError("Location hierarchy contains unresolved parents.")
            for source_id in ready:
                item = normalized[source_id]
                parent_source_id = item["parent_source_id"]
                parent = resolved.get(parent_source_id) if parent_source_id else None
                location = resolved.get(source_id)
                if location is None:
                    location = AdministrativeLocation(
                        source_id=source_id,
                        name=item["name"],
                        level=item["level"],
                        parent=parent,
                    )
                    location.save()
                    created_count += 1
                else:
                    new_parent_id = parent.pk if parent else None
                    if location.parent_id != new_parent_id and (
                        location.registrations.exists()
                        or location.administrator_scopes.exists()
                        or location.children.exists()
                    ):
                        raise CommandError(
                            f"Refusing to reparent in-use location {source_id!r}; "
                            "migrate registrations and administrator scopes explicitly first."
                        )
                    changed = (
                        location.name != item["name"]
                        or location.level != item["level"]
                        or location.parent_id != new_parent_id
                        or not location.active
                    )
                    if changed:
                        location.name = item["name"]
                        location.level = item["level"]
                        location.parent = parent
                        location.active = True
                        location.save(update_fields=["name", "level", "parent", "active"])
                        updated_count += 1
                resolved[source_id] = location
                pending.remove(source_id)

        omitted_ids = set(existing) - set(normalized)
        if omitted_ids:
            AdministrativeLocation.objects.filter(source_id__in=omitted_ids).update(
                active=False
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created_count} locations; updated {updated_count}; "
                f"deactivated {len(omitted_ids)} omitted locations."
            )
        )

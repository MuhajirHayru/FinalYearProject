import posixpath
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from registrations.models import (
    AdministrativeLocation,
    AdministrativeLocationImport,
    LocationLevel,
)

HDX_DATASET_URL = "https://data.humdata.org/dataset/cod-ab-eth"
HDX_API_URL = "https://data.humdata.org/api/3/action/package_show?id=cod-ab-eth"
HDX_LICENSE = "CC BY-IGO"
EXPECTED_V04_COUNTS = {"eth_admin1": 15, "eth_admin2": 107, "eth_admin3": 1148}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column_index(reference):
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise CommandError(f"Invalid Excel cell reference {reference!r}.")
    index = 0
    for letter in letters.group():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _read_xlsx_sheets(path):
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CommandError(f"Cannot read HDX XLSX dataset: {exc}") from exc

    with archive:
        try:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
        except (KeyError, ElementTree.ParseError) as exc:
            raise CommandError("The file is not a valid Excel workbook.") from exc

        relationship_targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        try:
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                for item in shared_root.findall(f"{{{MAIN_NS}}}si")
            ]
        except KeyError:
            shared_strings = []
        except ElementTree.ParseError as exc:
            raise CommandError("The workbook shared-string table is invalid.") from exc

        sheets = {}
        for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
            sheet_name = sheet.attrib["name"]
            target = relationship_targets.get(sheet.attrib.get(f"{{{REL_NS}}}id"))
            if not target:
                raise CommandError(f"Workbook sheet {sheet_name!r} has no worksheet.")
            member = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            try:
                root = ElementTree.fromstring(archive.read(member))
            except (KeyError, ElementTree.ParseError) as exc:
                raise CommandError(f"Cannot read workbook sheet {sheet_name!r}.") from exc

            rows = []
            raw_rows = root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row")
            if not raw_rows:
                sheets[sheet_name] = rows
                continue
            header_values = {}
            for cell in raw_rows[0].findall(f"{{{MAIN_NS}}}c"):
                column = _column_index(cell.attrib["r"])
                header_values[column] = _cell_text(cell, shared_strings)
            headers = [header_values.get(index, "") for index in range(max(header_values) + 1)]
            for raw_row in raw_rows[1:]:
                values = {}
                for cell in raw_row.findall(f"{{{MAIN_NS}}}c"):
                    values[_column_index(cell.attrib["r"])] = _cell_text(
                        cell, shared_strings
                    )
                row = {
                    header: values.get(index, "").strip()
                    for index, header in enumerate(headers)
                    if header
                }
                if any(row.values()):
                    rows.append(row)
            sheets[sheet_name] = rows
        return sheets


def _cell_text(cell, shared_strings):
    inline = cell.find(f"{{{MAIN_NS}}}is")
    if inline is not None:
        return "".join(
            node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t")
        )
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError) as exc:
            raise CommandError("Workbook contains an invalid shared-string index.") from exc
    return value.text


def _alternatives(row, prefix):
    candidates = [
        row.get(f"{prefix}_name{number}", "")
        for number in range(1, 4)
    ]
    candidates.extend(
        (
            row.get(f"{prefix}_alt_name", ""),
            row.get(f"{prefix}_ref_name", ""),
        )
    )
    primary = row.get(f"{prefix}_name", "")
    return list(dict.fromkeys(value for value in candidates if value and value != primary))


class Command(BaseCommand):
    help = (
        "Import Ethiopia's OCHA/HDX COD-AB XLSX hierarchy (ADM1 regions/cities, "
        "ADM2 divisions, ADM3 woredas/locally named units)."
    )

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=Path)
        parser.add_argument("--source-version", default="v04")
        parser.add_argument("--source-url", default=HDX_DATASET_URL)
        parser.add_argument("--source-retrieved-on", type=date.fromisoformat, default=date.today())
        parser.add_argument("--reviewed-on", type=date.fromisoformat, default=date(2025, 12, 1))
        parser.add_argument(
            "--allow-count-changes",
            action="store_true",
            help="Required when an updated dataset changes the published v04 unit counts.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        sheets = _read_xlsx_sheets(options["xlsx_path"])
        required_sheets = set(EXPECTED_V04_COUNTS)
        missing = required_sheets - set(sheets)
        if missing:
            raise CommandError(f"HDX workbook is missing sheets: {', '.join(sorted(missing))}.")

        counts = {name: len(sheets[name]) for name in required_sheets}
        if options["source_version"].lower() == "v04" and counts != EXPECTED_V04_COUNTS:
            raise CommandError(
                f"Unexpected v04 source counts {counts}; expected {EXPECTED_V04_COUNTS}."
            )
        if counts != EXPECTED_V04_COUNTS and not options["allow_count_changes"]:
            raise CommandError(
                f"Dataset unit counts differ from v04: {counts}. Review the new source "
                "and rerun with --allow-count-changes only after verification."
            )

        location_rows = []
        region_codes = set()
        division_codes = set()
        for row in sheets["eth_admin1"]:
            code = row.get("adm1_pcode", "")
            name = row.get("adm1_name", "")
            if not code or not name or code in region_codes:
                raise CommandError("ADM1 rows contain blank names/codes or duplicate pcodes.")
            region_codes.add(code)
            city = code in ("ET14", "ET15")
            location_rows.append(
                self._location_row(
                    code,
                    name,
                    LocationLevel.CITY if city else LocationLevel.REGION,
                    None,
                    row,
                    "adm1",
                    active=code != "ET99",
                    source_url=options["source_url"],
                    source_version=options["source_version"],
                    verified_on=options["reviewed_on"],
                )
            )

        for row in sheets["eth_admin2"]:
            code = row.get("adm2_pcode", "")
            parent_code = row.get("adm1_pcode", "")
            name = row.get("adm2_name", "")
            if (
                not code
                or not name
                or code in division_codes
                or parent_code not in region_codes
            ):
                raise CommandError(
                    f"ADM2 has a missing/duplicate pcode or invalid ADM1 parent: {code!r}."
                )
            division_codes.add(code)
            parent_name = next(
                item["adm1_name"] for item in sheets["eth_admin1"]
                if item["adm1_pcode"] == parent_code
            )
            if row.get("adm1_name") != parent_name:
                raise CommandError(f"ADM2 parent name mismatch for {code!r}.")
            if parent_code == "ET14":
                level = LocationLevel.OTHER
            elif parent_code == "ET15":
                level = LocationLevel.DISTRICT
            else:
                level = LocationLevel.ZONE
            location_rows.append(
                self._location_row(
                    code,
                    name,
                    level,
                    parent_code,
                    row,
                    "adm2",
                    active=parent_code != "ET99",
                    source_url=options["source_url"],
                    source_version=options["source_version"],
                    verified_on=options["reviewed_on"],
                )
            )

        woreda_codes = set()
        for row in sheets["eth_admin3"]:
            code = row.get("adm3_pcode", "")
            parent_code = row.get("adm2_pcode", "")
            region_code = row.get("adm1_pcode", "")
            name = row.get("adm3_name", "")
            if (
                not code
                or not name
                or code in woreda_codes
                or parent_code not in division_codes
            ):
                raise CommandError(
                    f"ADM3 has a missing/duplicate pcode or invalid ADM2 parent: {code!r}."
                )
            woreda_codes.add(code)
            parent_row = next(
                item for item in sheets["eth_admin2"]
                if item["adm2_pcode"] == parent_code
            )
            if parent_row["adm1_pcode"] != region_code:
                raise CommandError(f"ADM3 parent chain mismatch for {code!r}.")
            if region_code == "ET14":
                level = LocationLevel.SUBCITY
            elif region_code == "ET15" or region_code == "ET99":
                level = LocationLevel.OTHER
            else:
                level = LocationLevel.WOREDA
            location_rows.append(
                self._location_row(
                    code,
                    name,
                    level,
                    parent_code,
                    row,
                    "adm3",
                    active=region_code != "ET99",
                    source_url=options["source_url"],
                    source_version=options["source_version"],
                    verified_on=options["reviewed_on"],
                )
            )

        all_source_codes = {row["source_id"] for row in location_rows}
        for row in location_rows:
            if row["parent_source_id"] and row["parent_source_id"] not in all_source_codes:
                raise CommandError(
                    f"Location {row['source_id']!r} refers to a missing source parent."
                )

        existing = {
            item.source_id: item
            for item in AdministrativeLocation.objects.select_related("parent")
            .filter(source_id__startswith="HDX-COD-AB-ETH:")
        }
        resolved = {}
        created_count = updated_count = unchanged_count = inactive_count = 0
        for row in location_rows:
            parent = resolved.get(row["parent_source_id"])
            if row["parent_source_id"] and parent is None:
                raise CommandError(
                    f"Parent {row['parent_source_id']!r} was not imported before "
                    f"{row['source_id']!r}."
                )
            location = existing.get(row["source_id"])
            if location is None:
                values = {
                    key: value for key, value in row.items()
                    if key != "parent_source_id"
                }
                location = AdministrativeLocation(**values, parent=parent)
                location.save()
                created_count += 1
            else:
                new_values = {
                    **row,
                    "parent_id": parent.pk if parent else None,
                }
                in_use = (
                    location.registrations.exists()
                    or location.administrator_scopes.exists()
                    or location.children.exists()
                )
                relationship_changed = (
                    location.parent_id != new_values["parent_id"]
                    or location.level != row["level"]
                )
                if in_use and relationship_changed:
                    raise CommandError(
                        f"Refusing to change the parent or administrative level of "
                        f"in-use location {row['source_id']!r}."
                    )
                changed_fields = [
                    key
                    for key, value in row.items()
                    if key != "parent_source_id" and getattr(location, key) != value
                ]
                if location.parent_id != new_values["parent_id"]:
                    changed_fields.append("parent")
                if changed_fields:
                    for key, value in row.items():
                        setattr(location, key, value)
                    location.parent = parent
                    location.save(update_fields=changed_fields)
                    updated_count += 1
                else:
                    unchanged_count += 1
            if not row["active"]:
                inactive_count += 1
            resolved[row["source_id"]] = location

        excluded = [
            row["source_id"]
            for row in location_rows
            if not row["active"]
        ]
        coverage = {
            "source_admin_level_counts": counts,
            "selectable_location_count": len(location_rows) - inactive_count,
            "inactive_contested_pcodes": excluded,
            "kebele_units_in_source": 0,
            "kebele_coverage": (
                "Not provided by this COD-AB release; no kebele units were inferred."
            ),
            "addis_ababa": (
                "Source hierarchy contains Addis Ababa > Region 14 > 11 Sub City units; "
                "the source does not identify a Kifle Ketema unit."
            ),
            "dire_dawa": (
                "Source hierarchy contains Dire Dawa urban and rural ADM2 divisions, "
                "with locally named ADM3 children."
            ),
            "contested_boundary_caveat": (
                "The source marks Dawe Serer (ET042199) and Quarsadula (ET050905) as "
                "not representable on maps; those units are not present in the boundary "
                "workbook and have not been fabricated."
            ),
            "license": HDX_LICENSE,
            "disclaimer": (
                "Names and boundaries are for reference and do not imply UN endorsement; "
                "the source warns they may not reflect current administrative realities."
            ),
        }
        AdministrativeLocationImport.objects.create(
            source_name="OCHA/HDX Ethiopia COD-AB",
            source_url=options["source_url"],
            source_version=options["source_version"],
            source_retrieved_on=options["source_retrieved_on"],
            reviewed_on=options["reviewed_on"],
            record_count=len(location_rows),
            created_count=created_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            inactive_count=inactive_count,
            coverage_report=coverage,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(location_rows)} source records: {created_count} created, "
                f"{updated_count} updated, {unchanged_count} unchanged; "
                f"{inactive_count} contested records inactive."
            )
        )
        self.stdout.write(
            f"Source: {options['source_url']} | version {options['source_version']} | "
            f"retrieved {options['source_retrieved_on'].isoformat()} | "
            f"reviewed {options['reviewed_on'].isoformat()} | {HDX_LICENSE}"
        )
        self.stdout.write(
            "Coverage limitation: no kebele records are provided by this dataset."
        )

    @staticmethod
    def _location_row(
        code,
        name,
        level,
        parent_code,
        source_row,
        prefix,
        active,
        source_url,
        source_version,
        verified_on,
    ):
        alternatives = _alternatives(source_row, prefix)
        return {
            "source_id": f"HDX-COD-AB-ETH:{code}",
            "name": name,
            "alternative_names": alternatives,
            "level": level,
            "parent_source_id": (
                f"HDX-COD-AB-ETH:{parent_code}" if parent_code else None
            ),
            "active": active,
            "source_url": source_url,
            "source_version": source_version,
            "verified_on": verified_on,
        }

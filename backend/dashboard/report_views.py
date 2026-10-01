"""Financial report generation and export (FR-FM-03, FR-FM-04).

Reports are produced by the ReportService: an aggregation layer that returns a
single filterable result set, which the summary view renders as JSON and the
export views render as CSV or PDF.  Both exports consume the *same* queryset so
a downloaded file always matches what the Financial Manager previewed.
"""
import csv
import io
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from payments.models import PaymentRecord, PaymentStatus
from users.permissions import IsFinancialManager

CSV_HEADERS = [
    "Payment ID", "Wholesaler", "Farmer", "Product", "Amount (ETB)",
    "Method", "Reference", "Status", "Submitted", "Verified",
]

REPORT_FORMATS = ("json", "csv", "pdf")


class ReportService:
    """Filter + aggregate the payment ledger for reporting."""

    @staticmethod
    def filter(params):
        qs = PaymentRecord.objects.select_related(
            "submitted_by", "farmer", "product", "verified_by"
        )

        status_param = params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)

        method = params.get("method")
        if method and method != "ALL":
            qs = qs.filter(payment_method=method)

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(submitted_at__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(submitted_at__date__lte=date_to)

        user_id = params.get("user_id")
        if user_id:
            qs = qs.filter(
                Q(submitted_by_id=user_id) | Q(farmer_id=user_id)
            )

        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(reference_number__icontains=search)
                | Q(product__title__icontains=search)
                | Q(submitted_by__full_name__icontains=search)
                | Q(farmer__full_name__icontains=search)
            )
        return qs

    @staticmethod
    def summarise(qs):
        by_status = {
            row["status"]: {
                "count": row["c"],
                "total": int(row["t"] or 0),
            }
            for row in qs.values("status").annotate(c=Count("id"), t=Sum("amount"))
        }
        by_method = {
            row["payment_method"]: {
                "count": row["c"],
                "total": int(row["t"] or 0),
            }
            for row in qs.values("payment_method").annotate(c=Count("id"), t=Sum("amount"))
        }
        by_farmer = [
            {
                "farmer": row["farmer__full_name"],
                "count": row["c"],
                "total": int(row["t"] or 0),
            }
            for row in qs.values("farmer__full_name")
            .annotate(c=Count("id"), t=Sum("amount"))
            .order_by("-t")[:10]
        ]
        by_wholesaler = [
            {
                "wholesaler": row["submitted_by__full_name"],
                "count": row["c"],
                "total": int(row["t"] or 0),
            }
            for row in qs.values("submitted_by__full_name")
            .annotate(c=Count("id"), t=Sum("amount"))
            .order_by("-t")[:10]
        ]
        grand_total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        return {
            "count": qs.count(),
            "amount": int(grand_total),
            "by_status": by_status,
            "by_method": by_method,
            "top_farmers": by_farmer,
            "top_wholesalers": by_wholesaler,
        }

    @staticmethod
    def rows(qs):
        for p in qs:
            yield [
                p.display_id,
                p.submitted_by.full_name,
                p.farmer.full_name,
                p.product.title,
                str(p.amount),
                p.payment_method,
                p.reference_number,
                p.status,
                p.submitted_at.strftime("%Y-%m-%d %H:%M"),
                p.verified_at.strftime("%Y-%m-%d %H:%M") if p.verified_at else "",
            ]


def _as_csv(qs):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    writer.writerows(ReportService.rows(qs))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Minimal PDF writer — avoids adding a binary dependency for a text report.
# ---------------------------------------------------------------------------
def _pdf_escape(text):
    return str(text).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _as_pdf(title, summary, qs, max_rows=200):
    lines = [title, "=" * len(title), ""]
    lines.append(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')} (Africa/Addis_Ababa)")
    lines.append(f"Transactions: {summary['count']}")
    lines.append(f"Total amount: {summary['amount']:,} ETB")
    lines.append("")

    lines.append("By status")
    for key, value in summary["by_status"].items():
        lines.append(f"  {key:<10} {value['count']:>5}   {value['total']:>14,} ETB")
    lines.append("")
    lines.append("By method")
    for key, value in summary["by_method"].items():
        lines.append(f"  {key:<15} {value['count']:>5}   {value['total']:>14,} ETB")
    lines.append("")
    lines.append("Detail")
    lines.append("  " + " | ".join(CSV_HEADERS))
    for index, row in enumerate(ReportService.rows(qs)):
        if index >= max_rows:
            lines.append(f"  ... truncated at {max_rows} rows")
            break
        lines.append("  " + " | ".join(row))

    content_lines = [f"({_pdf_escape(line)}) Tj" for line in lines]
    stream = "\n".join(["BT", "/F1 9 Tf", "40 800 Td", "11 TL", *content_lines, "ET"])

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1", "replace")

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


def _filename(extension):
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"greenpath_financial_report_{stamp}.{extension}"


def _download(content, content_type, extension):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{_filename(extension)}"'
    return response


@extend_schema(responses=OpenApiTypes.OBJECT)
class FinancialSummaryView(APIView):
    """GET /api/v1/reports/financial-summary/ (FR-FM-03)."""

    permission_classes = [IsFinancialManager]

    def get(self, request):
        qs = ReportService.filter(request.query_params)
        return Response(
            {
                "success": True,
                "generated_at": timezone.now(),
                "filters": {
                    k: v
                    for k, v in request.query_params.items()
                    if k in ("status", "method", "date_from", "date_to", "user_id")
                },
                "totals": ReportService.summarise(qs),
            }
        )


@extend_schema(responses=OpenApiTypes.OBJECT)
class FinancialExportView(APIView):
    """GET /api/v1/reports/financial-summary/export/?file_format=csv|pdf (FR-FM-04).

    Defaults to CSV when ``file_format`` is omitted.  The parameter is named
    ``file_format`` rather than ``format`` because DRF reserves ``?format=`` for
    content negotiation, which would reject unknown renderer names with a 404
    before this view ever runs.
    """

    permission_classes = [IsFinancialManager]

    def get(self, request):
        export_format = (
            request.query_params.get("file_format")
            or request.query_params.get("format")
            or "csv"
        ).lower()
        if export_format not in REPORT_FORMATS:
            return Response(
                {
                    "success": False,
                    "error": f"file_format must be one of {', '.join(REPORT_FORMATS)}.",
                },
                status=400,
            )

        qs = ReportService.filter(request.query_params)

        if export_format == "csv":
            return _download(_as_csv(qs), "text/csv", "csv")
        if export_format == "pdf":
            summary = ReportService.summarise(qs)
            return _download(
                _as_pdf("Green Path - Financial Summary", summary, qs),
                "application/pdf",
                "pdf",
            )
        return Response({"success": True, "totals": ReportService.summarise(qs)})


@extend_schema(responses=OpenApiTypes.OBJECT)
class TransactionVolumeView(APIView):
    """GET /api/v1/reports/transaction-volume/ — daily series for charts."""

    permission_classes = [IsFinancialManager]

    def get(self, request):
        days = min(int(request.query_params.get("days", 30)), 365)
        since = timezone.now() - timezone.timedelta(days=days)
        rows = (
            ReportService.filter(request.query_params)
            .filter(submitted_at__gte=since)
            .extra(select={"day": "DATE(submitted_at)"})
            .values_list("day")
            .annotate(
                c=Count("id"), t=Sum("amount")
            )
            .order_by("day")
        )
        return Response(
            {
                "success": True,
                "days": days,
                "series": [
                    {"date": r[0], "count": r[1], "total": int(r[2] or 0)} for r in rows
                ],
            }
        )

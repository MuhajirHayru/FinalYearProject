"""Financial Manager reports for completed wallet ledger activity."""
import csv
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import (
    FundingStatus,
    PayoutStatus,
    WalletFundingRequest,
    WalletPayoutRequest,
    WalletTransaction,
    WalletTransactionType,
)
from users.models import Role
from users.permissions import IsFinancialManager

PARTICIPANT_ROLES = (Role.FARMER, Role.WHOLESALER, Role.RETAILER)
COMPLETED_TYPES = (WalletTransactionType.FUNDING, WalletTransactionType.PAYOUT)


def _report_period(params):
    today = timezone.localdate()
    raw_from = params.get("date_from")
    raw_to = params.get("date_to")
    parsed_from = parse_date(raw_from) if raw_from else None
    parsed_to = parse_date(raw_to) if raw_to else None
    if raw_from and parsed_from is None:
        raise ValidationError({"date_from": "Use YYYY-MM-DD."})
    if raw_to and parsed_to is None:
        raise ValidationError({"date_to": "Use YYYY-MM-DD."})
    date_to = parsed_to or today
    date_from = parsed_from or date_to - timedelta(days=6)
    if date_from > date_to:
        raise ValidationError({"date_to": "Must be on or after date_from."})
    if (date_to - date_from).days > 365:
        raise ValidationError({"date_to": "The report period cannot exceed 366 days."})
    return date_from, date_to


def _activity_queryset(date_from, date_to):
    return WalletTransaction.objects.filter(
        wallet__user__role__in=PARTICIPANT_ROLES,
        transaction_type__in=COMPLETED_TYPES,
        created_at__date__range=(date_from, date_to),
    )


def _status_breakdown(queryset, statuses):
    rows = queryset.values("status").annotate(
        count=Count("id"),
        amount=Sum("amount"),
    )
    totals = {
        row["status"]: {
            "count": row["count"],
            "amount": str(row["amount"] or Decimal("0.00")),
        }
        for row in rows
    }
    return {
        status: totals.get(
            status,
            {"count": 0, "amount": "0.00"},
        )
        for status, _label in statuses
    }


def _csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


class WalletActivityReportView(APIView):
    permission_classes = [IsFinancialManager]

    def get(self, request):
        date_from, date_to = _report_period(request.query_params)
        activity = _activity_queryset(date_from, date_to)
        daily_totals = defaultdict(
            lambda: {
                "deposits": Decimal("0.00"),
                "payouts": Decimal("0.00"),
                "deposit_count": 0,
                "payout_count": 0,
            }
        )
        aggregates = activity.values(
            "transaction_type", day=TruncDate("created_at")
        ).annotate(total=Sum("amount"), count=Count("id"))
        completed = {
            "deposits": {"amount": Decimal("0.00"), "count": 0},
            "payouts": {"amount": Decimal("0.00"), "count": 0},
        }
        type_to_key = {
            WalletTransactionType.FUNDING: "deposits",
            WalletTransactionType.PAYOUT: "payouts",
        }
        for row in aggregates:
            key = type_to_key[row["transaction_type"]]
            day = row["day"]
            total = row["total"] or Decimal("0.00")
            daily_totals[day][key] += total
            daily_totals[day][f"{key[:-1]}_count"] += row["count"]
            completed[key]["amount"] += total
            completed[key]["count"] += row["count"]

        daily = []
        current_day = date_from
        while current_day <= date_to:
            values = daily_totals[current_day]
            daily.append(
                {
                    "date": current_day.isoformat(),
                    "deposits": str(values["deposits"]),
                    "payouts": str(values["payouts"]),
                    "deposit_count": values["deposit_count"],
                    "payout_count": values["payout_count"],
                }
            )
            current_day += timedelta(days=1)

        funding = WalletFundingRequest.objects.filter(
            wallet__user__role__in=PARTICIPANT_ROLES,
            submitted_at__date__range=(date_from, date_to),
        )
        payouts = WalletPayoutRequest.objects.filter(
            wallet__user__role__in=PARTICIPANT_ROLES,
            submitted_at__date__range=(date_from, date_to),
        )
        response = Response(
            {
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                },
                "summary": completed,
                "status_breakdown": {
                    "deposits": _status_breakdown(funding, FundingStatus.choices),
                    "payouts": _status_breakdown(payouts, PayoutStatus.choices),
                },
                "daily": daily,
            }
        )
        response["Cache-Control"] = "no-store"
        return response


class _CsvBuffer:
    def write(self, value):
        return value


class WalletActivityExportView(APIView):
    permission_classes = [IsFinancialManager]

    def get(self, request):
        date_from, date_to = _report_period(request.query_params)
        queryset = _activity_queryset(date_from, date_to).select_related(
            "wallet__user"
        ).order_by("created_at", "pk")

        def rows():
            writer = csv.writer(_CsvBuffer())
            yield writer.writerow(
                [
                    "Date",
                    "Activity",
                    "Wallet owner",
                    "Role",
                    "Amount (ETB)",
                    "Available delta",
                    "Held delta",
                    "Reference",
                    "External reference",
                    "Description",
                ]
            )
            for transaction in queryset.iterator(chunk_size=1000):
                yield writer.writerow(
                    [
                        transaction.created_at.isoformat(),
                        transaction.get_transaction_type_display(),
                        _csv_cell(transaction.wallet.user.full_name),
                        transaction.wallet.user.role,
                        transaction.amount,
                        transaction.available_delta,
                        transaction.held_delta,
                        _csv_cell(transaction.reference),
                        _csv_cell(transaction.external_reference),
                        _csv_cell(transaction.description),
                    ]
                )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="wallet-activity-{date_from}-{date_to}.csv"'
        )
        response["Cache-Control"] = "no-store"
        return response

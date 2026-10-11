from datetime import date
from pathlib import Path

from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, views
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from notifications.services import notify
from products.models import Category
from users.models import AccountStatus, AuditLog, PlatformSettings, Role, User

from .authentication import RegistrationCompletionAuthentication
from .models import (
    AgriculturalProductType,
    AdministratorScope,
    AdministrativeLocation,
    RegistrationDocument,
    RegistrationReview,
    RegistrationStatus,
    UserRegistration,
)
from .serializers import (
    AgriculturalProductTypeSerializer,
    LicenseVerificationSerializer,
    LocationSerializer,
    RegistrationDecisionSerializer,
    RegistrationDetailsSerializer,
    RegistrationDocumentSerializer,
    RegistrationDocumentUploadSerializer,
    RegistrationDraftSerializer,
    RegistrationSubmissionSerializer,
    registration_can_be_submitted,
)
from .services import (
    manageable_admins_for,
    location_descendant_ids,
    record_registration_decision,
    users_visible_to_admin,
)


class LocationOptionsView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = LocationSerializer
    pagination_class = None

    def get_queryset(self):
        parent_id = self.request.query_params.get("parent_id")
        queryset = AdministrativeLocation.objects.filter(active=True)
        if parent_id:
            parent = get_object_or_404(queryset, pk=parent_id)
            return queryset.filter(parent=parent).order_by("name", "source_id")
        return queryset.filter(parent__isnull=True).order_by("name", "source_id")


class ProductTypeOptionsView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = AgriculturalProductTypeSerializer
    pagination_class = None
    queryset = AgriculturalProductType.objects.filter(
        active=True,
        category__in=(Category.VEGETABLES, Category.ROOT_CROPS, Category.FRUITS),
    ).order_by("category", "name")


class RegistrationDraftView(views.APIView):
    authentication_classes = [RegistrationCompletionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_registration(self, user):
        return get_object_or_404(
            UserRegistration.objects.select_related("location", "user").prefetch_related(
                "documents", "product_selections__product_type", "review_history__reviewer"
            ),
            user=user,
        )

    def get(self, request):
        registration = self.get_registration(request.user)
        return Response(RegistrationDetailsSerializer(registration).data)

    def patch(self, request):
        registration = self.get_registration(request.user)
        if registration.status not in (
            RegistrationStatus.DRAFT,
            RegistrationStatus.CHANGES_REQUESTED,
            RegistrationStatus.REJECTED,
        ):
            return Response(
                {"success": False, "error": "This registration can no longer be edited."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = RegistrationDraftSerializer(
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            registration = serializer.update(
                registration, serializer.validated_data
            )
        return Response(RegistrationDetailsSerializer(registration).data)


class RegistrationDocumentView(views.APIView):
    authentication_classes = [RegistrationCompletionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        registration = get_object_or_404(UserRegistration, user=request.user)
        serializer = RegistrationDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        document_type = {
            Role.FARMER: "FARMER_LICENSE",
            Role.WHOLESALER: "WHOLESALER_LICENSE",
            Role.RETAILER: "RETAILER_LICENSE",
        }[request.user.role]
        document = RegistrationDocument.objects.create(
            registration=registration,
            document_type=document_type,
            original_filename=Path(uploaded.name).name[:255],
            file=uploaded,
        )
        return Response(
            RegistrationDocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, document_id):
        registration = get_object_or_404(UserRegistration, user=request.user)
        document = get_object_or_404(
            RegistrationDocument, id=document_id, registration=registration
        )
        document.file.delete(save=False)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitRegistrationView(views.APIView):
    authentication_classes = [RegistrationCompletionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        registration = get_object_or_404(
            UserRegistration.objects.select_related("location", "user"),
            user=request.user,
        )
        serializer = RegistrationSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration_can_be_submitted(registration, request.user)

        config = PlatformSettings.load()
        with transaction.atomic():
            registration.status = RegistrationStatus.SUBMITTED
            registration.submitted_at = timezone.now()
            registration.save(update_fields=["status", "submitted_at", "updated_at"])

            if request.user.status == AccountStatus.REJECTED:
                request.user.status = AccountStatus.PENDING
                request.user.rejection_reason = ""
                request.user.is_active = False
                request.user.save(
                    update_fields=["status", "rejection_reason", "is_active", "updated_at"]
                )

            if not config.require_approval:
                registration.status = RegistrationStatus.APPROVED
                registration.save(update_fields=["status", "updated_at"])
                request.user.approve()
            else:
                reviewers = _reviewer_ids_for_registration(registration)
                if reviewers:
                    notify(
                        user_ids=reviewers,
                        type="REGISTRATION",
                        message=(
                            f"New {request.user.get_role_display().lower()} registration "
                            f"awaiting review: {request.user.full_name}"
                        ),
                        actor=request.user,
                    )
                notify(
                    user_ids=[request.user.id],
                    type="REGISTRATION",
                    message="Your complete registration was submitted for admin review.",
                    actor=None,
                )
        return Response(
            {
                "success": True,
                "message": (
                    "Registration complete and approved."
                    if not config.require_approval
                    else "Registration submitted. It is awaiting admin review."
                ),
                "status": registration.status,
            }
        )


def _reviewer_ids_for_registration(registration):
    candidates = User.objects.filter(role=Role.SUPER_ADMIN, status=AccountStatus.APPROVED)
    scopes = AdministratorScope.objects.filter(
        user__status=AccountStatus.APPROVED
    ).select_related("location")
    location_ids = set()
    location = registration.location
    while location is not None:
        location_ids.add(location.pk)
        location = location.parent
    scoped_user_ids = scopes.filter(
        Q(level=AdministratorScope.Level.GLOBAL)
        | Q(level=AdministratorScope.Level.LOCATION, location_id__in=location_ids)
    ).values_list("user_id", flat=True)
    return list(set(candidates.values_list("id", flat=True)) | set(scoped_user_ids))


def _scoped_registrations(user):
    visible_users = users_visible_to_admin(user)
    return UserRegistration.objects.filter(user__in=visible_users).select_related(
        "user", "location", "location__parent"
    ).prefetch_related(
        "documents", "product_selections__product_type", "review_history__reviewer"
    )


def _filter_registrations(queryset, params):
    role = params.get("role")
    if role:
        if role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
            raise ValidationError({"role": "Choose a commercial registration role."})
        queryset = queryset.filter(user__role=role)
    registration_status = params.get("status")
    if registration_status:
        valid_statuses = {choice.value for choice in RegistrationStatus}
        if registration_status not in valid_statuses:
            raise ValidationError({"status": "Unknown registration status."})
        queryset = queryset.filter(status=registration_status)
    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(user__full_name__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__phone__icontains=search)
            | Q(location__name__icontains=search)
        )
    location_id = params.get("location_id")
    if location_id:
        location = get_object_or_404(AdministrativeLocation, pk=location_id, active=True)
        queryset = queryset.filter(location_id__in=location_descendant_ids(location))
    for parameter, lookup in (
        ("submitted_from", "submitted_at__date__gte"),
        ("submitted_to", "submitted_at__date__lte"),
    ):
        raw = params.get(parameter)
        if raw:
            try:
                date.fromisoformat(raw)
            except ValueError as exc:
                raise ValidationError({parameter: "Use an ISO date (YYYY-MM-DD)."}) from exc
            queryset = queryset.filter(**{lookup: raw})
    return queryset


class RegistrationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RegistrationDetailsSerializer

    def get_queryset(self):
        if self.request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return UserRegistration.objects.none()
        queryset = _scoped_registrations(self.request.user)
        if not self.request.query_params.get("status"):
            queryset = queryset.filter(
                status__in=(
                    RegistrationStatus.SUBMITTED,
                    RegistrationStatus.CHANGES_REQUESTED,
                )
            )
        return _filter_registrations(queryset, self.request.query_params)


class RegistrationDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RegistrationDetailsSerializer
    lookup_url_kwarg = "registration_id"

    def get_queryset(self):
        if self.request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return UserRegistration.objects.none()
        return _scoped_registrations(self.request.user)


class RegistrationDecisionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, registration_id):
        if request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        registration = get_object_or_404(
            _scoped_registrations(request.user),
            pk=registration_id,
        )
        serializer = RegistrationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data["reason"]
        registration = record_registration_decision(
            registration.pk,
            request.user,
            action,
            reason,
        )
        return Response(
            {
                "success": True,
                "registration": RegistrationDetailsSerializer(registration).data,
            }
        )


class RegistrationDocumentAccessView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, document_id):
        if request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        document = get_object_or_404(
            RegistrationDocument.objects.select_related(
                "registration__user", "registration__location"
            ),
            pk=document_id,
        )
        if not users_visible_to_admin(request.user).filter(
            pk=document.registration.user_id
        ).exists():
            raise NotFound()
        extension = Path(document.original_filename).suffix.lower()
        content_type = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }[extension]
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=Path(document.original_filename).name,
            content_type=content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class VerifyRegistrationDocumentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, document_id):
        if request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        document = get_object_or_404(
            RegistrationDocument.objects.select_related("registration__user"),
            pk=document_id,
        )
        if not users_visible_to_admin(request.user).filter(
            pk=document.registration.user_id
        ).exists():
            raise NotFound()
        serializer = LicenseVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verified = serializer.validated_data["verified"]
        note = serializer.validated_data.get("note", "").strip()
        with transaction.atomic():
            document.verification_status = (
                RegistrationDocument.VerificationStatus.VERIFIED
                if verified
                else RegistrationDocument.VerificationStatus.REJECTED
            )
            document.verification_note = note
            document.verified_by = request.user
            document.verified_at = timezone.now()
            document.save(
                update_fields=[
                    "verification_status",
                    "verification_note",
                    "verified_by",
                    "verified_at",
                ]
            )
            RegistrationReview.objects.create(
                registration=document.registration,
                reviewer=request.user,
                action=(
                    RegistrationReview.Action.LICENSE_VERIFIED
                    if verified
                    else RegistrationReview.Action.LICENSE_REJECTED
                ),
                reason=note,
            )
            AuditLog.objects.create(
                actor=request.user,
                action="registration_license_verified" if verified else "registration_license_rejected",
                target=document.registration.user.email,
                detail=note,
            )
            if not verified:
                notify(
                    user_ids=[document.registration.user_id],
                    type="REGISTRATION",
                    message=f"Your license needs correction. Reason: {note}",
                    actor=request.user,
                )
        return Response(RegistrationDocumentSerializer(document).data)


class RegistrationReportView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        queryset = _scoped_registrations(request.user)
        queryset = _filter_registrations(queryset, request.query_params)
        rows = queryset.values("status", "user__role").annotate(total=Count("id"))
        by_status = {value: 0 for value, _ in RegistrationStatus.choices}
        by_role = {value: 0 for value, _ in Role.choices}
        for row in rows:
            by_status[row["status"]] += row["total"]
            by_role[row["user__role"]] += row["total"]
        return Response(
            {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "by_role": by_role,
            }
        )


class AdministratorScopeListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return AdministratorScope.objects.none()
        visible_users = manageable_admins_for(
            self.request.user,
            User.objects.all(),
        ).values("pk")
        return (
            AdministratorScope.objects.select_related("user", "location")
            .filter(user_id__in=visible_users)
            .order_by("user__full_name")
        )

    def get_serializer_class(self):
        from .serializers import AdminScopeSerializer

        return AdminScopeSerializer

    def perform_create(self, serializer):
        user = serializer.validated_data["user"]
        if user.status != AccountStatus.APPROVED:
            raise ValidationError({"user": "Only active User Admin accounts can be scoped."})
        existing = AdministratorScope.objects.filter(user=user).first()
        previous = (
            str(existing.location or "Nationwide")
            if existing
            else "Unassigned"
        )
        if existing:
            serializer.instance = existing
        scope = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action="admin_scope_assigned",
            target=user.email,
            detail=f"{previous} -> {scope.location or 'Nationwide'}",
        )


class AdministratorScopeDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "user_id"
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        if self.request.user.role not in (Role.USER_ADMIN, Role.SUPER_ADMIN):
            return AdministratorScope.objects.none()
        visible_users = manageable_admins_for(
            self.request.user,
            User.objects.all(),
        ).values("pk")
        return AdministratorScope.objects.select_related(
            "user", "location"
        ).filter(user_id__in=visible_users)

    def get_serializer_class(self):
        from .serializers import AdminScopeSerializer

        return AdminScopeSerializer

    def perform_update(self, serializer):
        previous = str(serializer.instance.location or "Nationwide")
        scope = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action="admin_scope_updated",
            target=scope.user.email,
            detail=f"{previous} -> {scope.location or 'Nationwide'}",
        )

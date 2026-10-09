from django.urls import path

from .views import (
    BusinessAgreementListView,
    ChapaFundingInitializeView,
    ChapaFundingVerifyView,
    ChapaWebhookView,
    BankAccountDetailView,
    BankAccountFullDetailsView,
    BankAccountListCreateView,
    BankAccountReviewFlagView,
    PayoutBankListView,
    ReviewListCreateView,
    WalletFundingRequestListCreateView,
    WalletFundingReviewView,
    WalletPayoutRequestListCreateView,
    WalletPayoutReviewView,
    WalletTransactionListView,
    WalletView,
)

urlpatterns = [
    path("chapa/webhook/", ChapaWebhookView.as_view(), name="chapa_webhook"),
    path("", WalletView.as_view(), name="wallet"),
    path("transactions/", WalletTransactionListView.as_view(), name="wallet_transactions"),
    path("banks/", PayoutBankListView.as_view(), name="payout_banks"),
    path("bank-accounts/", BankAccountListCreateView.as_view(), name="bank_accounts"),
    path(
        "bank-accounts/<uuid:pk>/",
        BankAccountDetailView.as_view(),
        name="bank_account_detail",
    ),
    path(
        "bank-accounts/<uuid:pk>/full-details/",
        BankAccountFullDetailsView.as_view(),
        name="bank_account_full_details",
    ),
    path(
        "bank-accounts/<uuid:pk>/require-review/",
        BankAccountReviewFlagView.as_view(),
        name="bank_account_require_review",
    ),
    path("funding/", WalletFundingRequestListCreateView.as_view(), name="wallet_funding"),
    path("funding/chapa/", ChapaFundingInitializeView.as_view(), name="chapa_funding"),
    path(
        "funding/<uuid:pk>/review/",
        WalletFundingReviewView.as_view(),
        name="wallet_funding_review",
    ),
    path(
        "funding/<uuid:pk>/verify/",
        ChapaFundingVerifyView.as_view(),
        name="chapa_funding_verify",
    ),
    path("payouts/", WalletPayoutRequestListCreateView.as_view(), name="wallet_payouts"),
    path(
        "payouts/<uuid:pk>/review/",
        WalletPayoutReviewView.as_view(),
        name="wallet_payout_review",
    ),
    path("agreements/", BusinessAgreementListView.as_view(), name="business_agreements"),
    path("reviews/", ReviewListCreateView.as_view(), name="reviews"),
]

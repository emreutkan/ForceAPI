from django.urls import path
from .views import (
    UserProfileView, UpdateHeightView, UpdateGenderView,
    UpdateWeightView, GetWeightHistoryView, DeleteWeightView,
    DataExportView, DataImportView, DeleteAccountView
)

urlpatterns = [
    path('me/', UserProfileView.as_view(), name='me'),
    path('me/delete/', DeleteAccountView.as_view(), name='delete_account'),
    path('height/', UpdateHeightView.as_view(), name='update_height'),
    path('weight/', UpdateWeightView.as_view(), name='update_weight'),
    path('weight/history/', GetWeightHistoryView.as_view(), name='get_weight_history'),
    path('weight/<int:weight_id>/', DeleteWeightView.as_view(), name='delete_weight'),
    path('gender/', UpdateGenderView.as_view(), name='update_gender'),
    path('data/export/', DataExportView.as_view(), name='data_export'),
    path('data/import/', DataImportView.as_view(), name='data_import'),
]

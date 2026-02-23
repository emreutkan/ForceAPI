from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from core.views import HealthCheckView, ApiRootView
from user.views import RevenueCatWebhookView

urlpatterns = [
    path('', ApiRootView.as_view(), name='api-root'),
    path('admin/', admin.site.urls),
    path('api/health/', HealthCheckView.as_view(), name='health-check'),
    path('api/webhooks/revenuecat/', RevenueCatWebhookView.as_view(), name='revenuecat-webhook'),
    path('api/user/', include('user.urls')),
    path('api/workout/', include('workout.urls')),
    path('api/chat/', include('ai_chat.urls')),
    path('api/exercise/', include('exercise.urls')),
    path('api/measurements/', include('body_measurements.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import connection
from django.core.cache import cache
from django.conf import settings
import time
from core.mixins import ConditionalGetMixin


class ApiRootView(APIView):
    """
    GET /
    Simple root response with API info and links to docs and health.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'name': 'ForceAPI',
            'docs': request.build_absolute_uri('/api/docs/'),
            'health': request.build_absolute_uri('/api/health/'),
            'schema': request.build_absolute_uri('/api/schema/'),
        }, status=status.HTTP_200_OK)


class HealthCheckView(ConditionalGetMixin, APIView):
    """
    GET /api/health/
    Health check endpoint for monitoring and deployment checks.
    Checks database connectivity, cache connectivity, and response times.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        start_time = time.time()
        health_status = {
            'status': 'healthy',
            'checks': {}
        }
        overall_healthy = True
        
        # Check database connectivity with timing
        db_start = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_time = (time.time() - db_start) * 1000  # Convert to milliseconds
            health_status['checks']['database'] = {
                'status': 'healthy',
                'message': 'Database connection successful',
                'response_time_ms': round(db_time, 2)
            }
        except Exception as e:
            overall_healthy = False
            health_status['status'] = 'unhealthy'
            health_status['checks']['database'] = {
                'status': 'unhealthy',
                'message': f'Database connection failed: {str(e)}',
                'response_time_ms': round((time.time() - db_start) * 1000, 2)
            }
        
        # Check cache connectivity with timing
        cache_start = time.time()
        try:
            test_key = 'health_check_test'
            cache.set(test_key, 'test_value', 10)
            cached_value = cache.get(test_key)
            if cached_value == 'test_value':
                cache.delete(test_key)
                cache_time = (time.time() - cache_start) * 1000  # Convert to milliseconds
                health_status['checks']['cache'] = {
                    'status': 'healthy',
                    'message': 'Cache connection successful',
                    'response_time_ms': round(cache_time, 2)
                }
            else:
                overall_healthy = False
                health_status['status'] = 'unhealthy'
                health_status['checks']['cache'] = {
                    'status': 'unhealthy',
                    'message': 'Cache read/write test failed',
                    'response_time_ms': round((time.time() - cache_start) * 1000, 2)
                }
        except Exception as e:
            overall_healthy = False
            health_status['status'] = 'unhealthy'
            health_status['checks']['cache'] = {
                'status': 'unhealthy',
                'message': f'Cache connection failed: {str(e)}',
                'response_time_ms': round((time.time() - cache_start) * 1000, 2)
            }
        
        # Calculate total response time
        total_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        health_status['response_time_ms'] = round(total_time, 2)
        
        # Add environment info (non-sensitive)
        health_status['environment'] = {
            'debug': settings.DEBUG,
            'timezone': str(settings.TIME_ZONE),
        }
        
        http_status = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(health_status, status=http_status)

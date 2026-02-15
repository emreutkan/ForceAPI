import json
import logging
import time
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger('utrack.requests')
error_logger = logging.getLogger('utrack')


def _safe_log_str(s: str, max_length: int | None = None) -> str:
    """Make string safe for logging on streams that may use cp1252 or other non-UTF-8 encoding."""
    if not isinstance(s, str):
        s = str(s)
    s = s.encode('ascii', errors='replace').decode('ascii')
    if max_length is not None and len(s) > max_length:
        s = s[:max_length] + '...'
    return s

class RequestResponseLogMiddleware(MiddlewareMixin):
    """
    Logs all HTTP requests and responses with timing information.
    Only logs request body/response for non-sensitive endpoints in production.
    """
    
    # Endpoints where we don't want to log request/response bodies (sensitive data)
    SENSITIVE_PATHS = [
        '/api/user/login/',
        '/api/user/register/',
        '/auth/',
        '/api/token/',
    ]
    
    def process_request(self, request):
        """Log incoming request. User is not logged here because auth (e.g. JWT) runs later in the stack."""
        request.start_time = time.time()
        ip = self.get_client_ip(request)
        logger.info(
            f"REQUEST: {request.method} {request.get_full_path()} | IP: {ip}"
        )
        
        # Log request body for non-sensitive endpoints (only in DEBUG mode or for specific endpoints)
        if request.body and not self._is_sensitive_path(request.path):
            try:
                body_str = request.body.decode('utf-8')
                if body_str and len(body_str) < 1000:  # Only log small bodies
                    try:
                        body_json = json.loads(body_str)
                        logger.debug(f"Request body: {json.dumps(body_json, indent=2)}")
                    except json.JSONDecodeError:
                        logger.debug(f"Request body: {body_str[:200]}")
            except Exception as e:
                logger.debug(f"Could not decode request body: {str(e)}")
        
        return None
    
    def process_response(self, request, response):
        """Log response with timing"""
        if not hasattr(request, 'start_time'):
            return response
        
        duration = int((time.time() - request.start_time) * 1000)  # Convert to milliseconds
        
        user = getattr(request, 'user', None)
        user_str = user.email if user and user.is_authenticated else 'anonymous'
        ip = self.get_client_ip(request)
        
        # Log response
        log_level = 'warning' if response.status_code >= 400 else 'info'
        log_message = (
            f"RESPONSE: {request.method} {request.get_full_path()} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration}ms | "
            f"User: {user_str} | IP: {ip}"
        )
        
        # Log response body in DEBUG mode (development)
        if settings.DEBUG and not self._is_sensitive_path(request.path):
            try:
                # Try to get response content
                if hasattr(response, 'content'):
                    content = response.content
                    if content:
                        try:
                            content_str = content.decode('utf-8')
                            # Only log if it's JSON and not too large
                            if content_str.startswith('{') or content_str.startswith('['):
                                try:
                                    response_json = json.loads(content_str)
                                    # Limit size to prevent huge logs; sanitize for Windows cp1252 log streams
                                    if len(content_str) < 5000:
                                        log_body = _safe_log_str(json.dumps(response_json, indent=2, ensure_ascii=False))
                                        logger.info(f"Response JSON:\n{log_body}")
                                    else:
                                        logger.info(f"Response JSON (truncated): {_safe_log_str(content_str, max_length=500)}...")
                                except json.JSONDecodeError:
                                    # Not JSON, log as text (truncated)
                                    logger.debug(f"Response body: {_safe_log_str(content_str, max_length=200)}")
                        except UnicodeDecodeError:
                            pass
            except Exception as e:
                logger.debug(f"Could not log response body: {str(e)}")
        
        if log_level == 'warning':
            logger.warning(log_message)
            # Log error details for 5xx errors
            if response.status_code >= 500:
                error_logger.error(
                    f"Server Error: {request.method} {request.get_full_path()} | "
                    f"Status: {response.status_code} | User: {user_str}"
                )
        else:
            logger.info(log_message)
        
        return response
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _is_sensitive_path(self, path):
        """Check if path contains sensitive data"""
        return any(sensitive in path for sensitive in self.SENSITIVE_PATHS)


















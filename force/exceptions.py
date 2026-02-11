"""
Custom exception handlers for consistent error responses across the API.
"""
from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.response import Response
import logging

logger = logging.getLogger('force')


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns standardized error responses.
    
    Format:
    {
        "error": "error_code",
        "message": "user-friendly message",
        "details": {...}  # optional additional details
    }
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Customize the response data structure
        custom_response_data = {
            'error': _get_error_code(response.status_code, exc),
            'message': _get_user_friendly_message(exc, response),
        }
        
        # Add details if available
        if hasattr(exc, 'detail'):
            if isinstance(exc.detail, dict):
                custom_response_data['details'] = exc.detail
            elif isinstance(exc.detail, list):
                custom_response_data['details'] = {'errors': exc.detail}
            else:
                custom_response_data['details'] = {'error': str(exc.detail)}
        elif response.data:
            custom_response_data['details'] = response.data
        
        # Log error for debugging (but not sensitive info)
        if response.status_code >= 500:
            logger.error(
                f"Server error: {exc.__class__.__name__} - {str(exc)}",
                exc_info=True
            )
        elif response.status_code >= 400:
            logger.warning(
                f"Client error: {exc.__class__.__name__} - {str(exc)}"
            )
        
        response.data = custom_response_data
    
    return response


def _get_error_code(status_code, exc):
    """Get error code based on status code and exception type."""
    error_code_map = {
        400: 'BAD_REQUEST',
        401: 'UNAUTHORIZED',
        403: 'FORBIDDEN',
        404: 'NOT_FOUND',
        405: 'METHOD_NOT_ALLOWED',
        406: 'NOT_ACCEPTABLE',
        409: 'CONFLICT',
        422: 'VALIDATION_ERROR',
        429: 'TOO_MANY_REQUESTS',
        500: 'INTERNAL_SERVER_ERROR',
        503: 'SERVICE_UNAVAILABLE',
    }
    
    # Check for specific exception types
    if hasattr(exc, 'default_code'):
        return exc.default_code.upper() if exc.default_code else error_code_map.get(status_code, 'ERROR')
    
    return error_code_map.get(status_code, 'ERROR')


def _get_user_friendly_message(exc, response):
    """Get user-friendly error message."""
    # If exception has a default_detail, use it
    if hasattr(exc, 'default_detail'):
        if isinstance(exc.default_detail, str):
            return exc.default_detail
        elif isinstance(exc.default_detail, dict):
            # For validation errors, create a summary message
            return 'Validation error. Please check the details.'
        elif isinstance(exc.default_detail, list):
            return 'Validation error. Please check the details.'
    
    # Default messages based on status code
    default_messages = {
        400: 'Bad request. Please check your input.',
        401: 'Authentication required. Please log in.',
        403: 'You do not have permission to perform this action.',
        404: 'The requested resource was not found.',
        405: 'Method not allowed for this endpoint.',
        406: 'Not acceptable. Please check your request format.',
        409: 'Conflict. The resource already exists or is in use.',
        422: 'Validation error. Please check your input.',
        429: 'Too many requests. Please try again later.',
        500: 'An internal server error occurred. Please try again later.',
        503: 'Service temporarily unavailable. Please try again later.',
    }
    
    return default_messages.get(response.status_code, 'An error occurred.')

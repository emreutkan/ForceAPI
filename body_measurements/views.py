from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.db.models import Max
from core.mixins import ConditionalGetMixin
from .models import BodyMeasurement
from .serializers import BodyMeasurementSerializer, CalculateBodyFatSerializer
import math

class BodyMeasurementPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100

class CreateBodyMeasurementView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        POST /api/measurements/create/
        Create a new body measurement record.
        Body fat is automatically calculated.
        If gender is not provided, uses user's gender from database.
        """
        data = request.data.copy()
        # If gender not provided, use user's gender from database
        if 'gender' not in data or not data.get('gender'):
            data['gender'] = request.user.gender or 'male'
        
        serializer = BodyMeasurementSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            # Set user from request
            measurement = serializer.save(user=request.user)
            return Response(BodyMeasurementSerializer(measurement).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GetBodyMeasurementsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = BodyMeasurementPagination

    def get_last_modified(self, request, **kwargs):
        return BodyMeasurement.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/measurements/
        Get all body measurements for the user, ordered by date (newest first).
        """
        measurements = BodyMeasurement.objects.filter(
            user=request.user
        ).select_related('user').order_by('-created_at')
        
        paginator = self.pagination_class()
        paginated_measurements = paginator.paginate_queryset(measurements, request)
        serializer = BodyMeasurementSerializer(paginated_measurements, many=True)
        return paginator.get_paginated_response(serializer.data)

class CalculateBodyFatMenView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        POST /api/measurements/calculate-body-fat/men/
        Calculate body fat percentage for men using US Navy method.
        
        Required: height (cm), weight (kg), waist (cm), neck (cm)
        Optional: gender (uses user's gender from database if not provided)
        """
        data = request.data.copy()
        # Use provided gender, or user's gender from database, or default to 'male'
        gender = data.get('gender') or request.user.gender or 'male'
        data['gender'] = gender
        
        serializer = CalculateBodyFatSerializer(data=data)
        if serializer.is_valid():
            height = float(serializer.validated_data['height'])
            waist = float(serializer.validated_data['waist'])
            neck = float(serializer.validated_data['neck'])
            calculated_gender = serializer.validated_data.get('gender', gender)
            
            # Validate measurements
            if waist <= neck:
                return Response({
                    'error': 'Invalid measurements: waist must be greater than neck'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # US Navy formula for men
            # 495 / (1.0324 - 0.19077 * log10(waist - neck) + 0.15456 * log10(height)) - 450
            try:
                log_waist_neck = math.log10(waist - neck)
                log_height = math.log10(height)
                
                denominator = 1.0324 - (0.19077 * log_waist_neck) + (0.15456 * log_height)
                
                if denominator <= 0:
                    return Response({
                        'error': 'Invalid calculation result'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                body_fat = (495 / denominator) - 450
                
                # Ensure reasonable range
                if body_fat < 0 or body_fat > 50:
                    return Response({
                        'error': 'Calculated body fat percentage is outside reasonable range (0-50%). Please check your measurements.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                return Response({
                    'body_fat_percentage': round(body_fat, 2),
                    'measurements': {
                        'height_cm': height,
                        'weight_kg': float(serializer.validated_data['weight']),
                        'waist_cm': waist,
                        'neck_cm': neck
                    },
                    'gender_used': calculated_gender,
                    'method': 'US Navy Method (Men)'
                })
                
            except (ValueError, TypeError, ZeroDivisionError) as e:
                return Response({
                    'error': f'Calculation error: {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CalculateBodyFatWomenView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        POST /api/measurements/calculate-body-fat/women/
        Calculate body fat percentage for women using US Navy method.
        
        Required: height (cm), weight (kg), waist (cm), neck (cm), hips (cm)
        Optional: gender (uses user's gender from database if not provided)
        """
        data = request.data.copy()
        # Use provided gender, or user's gender from database, or default to 'female' for this endpoint
        gender = data.get('gender') or request.user.gender or 'female'
        data['gender'] = gender
        
        serializer = CalculateBodyFatSerializer(data=data)
        if serializer.is_valid():
            height = float(serializer.validated_data['height'])
            waist = float(serializer.validated_data['waist'])
            neck = float(serializer.validated_data['neck'])
            calculated_gender = serializer.validated_data.get('gender', gender)
            
            # For women, hips is required
            if calculated_gender == 'female':
                if 'hips' not in serializer.validated_data or serializer.validated_data['hips'] is None:
                    return Response({
                        'error': 'Hips measurement is required for women'
                    }, status=status.HTTP_400_BAD_REQUEST)
                hips = float(serializer.validated_data['hips'])
            else:
                # For men, hips is optional
                hips = float(serializer.validated_data.get('hips', 0)) if serializer.validated_data.get('hips') else None
            
            # Validate measurements
            if calculated_gender == 'female':
                if (waist + hips) <= neck:
                    return Response({
                        'error': 'Invalid measurements: (waist + hips) must be greater than neck'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                if waist <= neck:
                    return Response({
                        'error': 'Invalid measurements: waist must be greater than neck'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # US Navy formula
            try:
                if calculated_gender == 'female':
                    # Women: 495 / (1.29579 - 0.35004 * log10(waist + hips - neck) + 0.22100 * log10(height)) - 450
                    log_waist_hips_neck = math.log10(waist + hips - neck)
                    log_height = math.log10(height)
                    
                    denominator = 1.29579 - (0.35004 * log_waist_hips_neck) + (0.22100 * log_height)
                    method_name = 'US Navy Method (Women)'
                else:
                    # Men: 495 / (1.0324 - 0.19077 * log10(waist - neck) + 0.15456 * log10(height)) - 450
                    log_waist_neck = math.log10(waist - neck)
                    log_height = math.log10(height)
                    
                    denominator = 1.0324 - (0.19077 * log_waist_neck) + (0.15456 * log_height)
                    method_name = 'US Navy Method (Men)'
                
                if denominator <= 0:
                    return Response({
                        'error': 'Invalid calculation result'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                body_fat = (495 / denominator) - 450
                
                # Ensure reasonable range
                if body_fat < 0 or body_fat > 50:
                    return Response({
                        'error': 'Calculated body fat percentage is outside reasonable range (0-50%). Please check your measurements.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                response_data = {
                    'body_fat_percentage': round(body_fat, 2),
                    'measurements': {
                        'height_cm': height,
                        'weight_kg': float(serializer.validated_data['weight']),
                        'waist_cm': waist,
                        'neck_cm': neck
                    },
                    'gender_used': calculated_gender,
                    'method': method_name
                }
                
                if calculated_gender == 'female' and hips:
                    response_data['measurements']['hips_cm'] = hips
                
                return Response(response_data)
                
            except (ValueError, TypeError, ZeroDivisionError) as e:
                return Response({
                    'error': f'Calculation error: {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

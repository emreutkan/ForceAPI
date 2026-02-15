from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Supplement, UserSupplement, UserSupplementLog
from .serializers import SupplementSerializer, UserSupplementSerializer, UserSupplementLogSerializer
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.db.models import Q, Max
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from core.mixins import ConditionalGetMixin

class SupplementPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

class SupplementListView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = SupplementPagination

    def get_last_modified(self, request, **kwargs):
        return Supplement.objects.filter(is_active=True).aggregate(Max("updated_at"))["updated_at__max"]

    # Cache this view for 15 minutes (60 seconds * 15) 
    # django keeps cached data in memory for 15 minutes so it doesn't have to hit the database every time
    # for multiple servers in production we can use redis to cache the data
    @method_decorator(cache_page(60*15))
    def get(self, request):
        query = request.query_params.get('search', None)
        if query:
            supplements = Supplement.objects.filter(
                is_active=True
            ).filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )
        else:
            supplements = Supplement.objects.filter(is_active=True)
        
        paginator = self.pagination_class()
        paginated_supplements = paginator.paginate_queryset(supplements, request)
        serializer = SupplementSerializer(paginated_supplements, many=True)
        return paginator.get_paginated_response(serializer.data)

class UserSupplementListCreateView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = SupplementPagination

    def get_last_modified(self, request, **kwargs):
        return UserSupplement.objects.filter(user=request.user, is_active=True).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        user_supplements = UserSupplement.objects.filter(
            user=request.user, 
            is_active=True
        ).select_related('supplement')
        
        paginator = self.pagination_class()
        paginated_supplements = paginator.paginate_queryset(user_supplements, request)
        serializer = UserSupplementSerializer(paginated_supplements, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserSupplementSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserSupplementLogListCreateView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='user_supplement_log_list',
        summary='List supplement logs',
        description='Get logs for a specific user supplement. Requires user_supplement_id query parameter.',
        parameters=[
            OpenApiParameter(
                name='user_supplement_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='ID of the user supplement to get logs for (required)',
                required=True
            )
        ],
        responses={
            200: UserSupplementLogSerializer(many=True),
            400: None,
            404: None
        }
    )
    def get_last_modified(self, request, **kwargs):
        user_supplement_id = request.query_params.get('user_supplement_id')
        if not user_supplement_id:
            return None
        return UserSupplementLog.objects.filter(
            user_supplement_id=user_supplement_id,
            user_supplement__user=request.user,
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        # Require user_supplement_id to filter by specific supplement
        user_supplement_id = request.query_params.get('user_supplement_id')
        
        if not user_supplement_id:
            return Response({
                'error': 'user_supplement_id is required. Use query parameter: ?user_supplement_id=<id>'
            }, status=status.HTTP_400_BAD_REQUEST)


        try:
            # Verify the user_supplement belongs to the user
            user_supplement = UserSupplement.objects.select_related('supplement').get(
                id=user_supplement_id, 
                user=request.user
            )
        except UserSupplement.DoesNotExist:
            return Response({'error': 'User supplement not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get logs for this specific supplement
        user_supplement_logs = UserSupplementLog.objects.filter(
            user=request.user,
            user_supplement_id=user_supplement_id
        ).select_related('user_supplement__supplement').order_by('-date', '-time')
        
        serializer = UserSupplementLogSerializer(user_supplement_logs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=UserSupplementLogSerializer,
        responses={201: UserSupplementLogSerializer, 400: None}
    )
    def post(self, request):
        user_supplement_id = request.data.get('user_supplement_id')
        if UserSupplementLog.logged_today(request.user, user_supplement_id):
            return Response({'error': 'You have already logged today'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = UserSupplementLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  
class UserSupplementLogTodayView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        today = timezone.now().date()
        return UserSupplementLog.objects.filter(user=request.user, date=today).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        today = timezone.now().date()
        
        # Get all supplement logs for today
        today_logs = UserSupplementLog.objects.filter(
            user=request.user,
            date=today
        ).select_related('user_supplement__supplement').order_by('-time')
        
        serializer = UserSupplementLogSerializer(today_logs, many=True)
        return Response({
            'date': today.isoformat(),
            'logs': serializer.data,
            'count': today_logs.count()
        })

class UserSupplementLogDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request, log_id):
        try:
            user_supplement_log = UserSupplementLog.objects.select_related(
                'user_supplement__supplement'
            ).get(id=log_id, user=request.user)
            user_supplement_log.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except UserSupplementLog.DoesNotExist:
            return Response({'error': 'Log not found'}, status=status.HTTP_404_NOT_FOUND)
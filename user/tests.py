import unittest
from io import StringIO
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from .models import UserProfile, WeightHistory

User = get_user_model()


@unittest.skip("Auth is handled by Supabase; no Django register/login/password-reset endpoints.")
class UserRegistrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_user(self):
        """Test user registration"""
        data = {
            'email': 'newuser@example.com',
            'password': 'testpass123',
            'password2': 'testpass123'
        }
        response = self.client.post('/api/user/register/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())

    def test_register_password_mismatch(self):
        """Test registration with mismatched passwords"""
        data = {
            'email': 'user@example.com',
            'password': 'testpass123',
            'password2': 'differentpass'
        }
        response = self.client.post('/api/user/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@unittest.skip("Auth is handled by Supabase; no Django login endpoint.")
class UserAuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_login(self):
        """Test user login"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        response = self.client.post('/api/user/login/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        data = {
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }
        response = self.client.post('/api/user/login/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserProfileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_get_profile(self):
        """Test getting user profile"""
        response = self.client.get('/api/user/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'test@example.com')

    def test_update_weight(self):
        """Test updating user weight"""
        data = {'weight': 75.5}
        response = self.client.post('/api/user/weight/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WeightHistory.objects.count(), 1)

    def test_get_weight_history(self):
        """Test getting weight history"""
        WeightHistory.objects.create(user=self.user, weight=75.0)
        response = self.client.get('/api/user/weight/history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProManagementCommandTestCase(TestCase):
    def test_grant_pro_sets_user_as_paid_pro(self):
        user = User.objects.create_user(
            email='pro@example.com',
            password='testpass123'
        )
        out = StringIO()

        call_command('grant_pro', '--email', user.email, '--days', '14', stdout=out)

        user.refresh_from_db()
        self.assertTrue(user.is_pro)
        self.assertIsNotNone(user.pro_until)
        self.assertGreater(user.pro_until, timezone.now() + timedelta(days=13))

    def test_grant_pro_permanent_clears_expiration(self):
        user = User.objects.create_user(
            email='permanent@example.com',
            password='testpass123'
        )

        call_command('grant_pro', '--email', user.email, '--permanent')

        user.refresh_from_db()
        self.assertTrue(user.is_pro)
        self.assertIsNone(user.pro_until)

    def test_refresh_pro_statuses_disables_only_expired_users(self):
        expired_user = User.objects.create_user(
            email='expired@example.com',
            password='testpass123',
            is_pro=True,
            pro_until=timezone.now() - timedelta(minutes=5)
        )
        active_user = User.objects.create_user(
            email='active@example.com',
            password='testpass123',
            is_pro=True,
            pro_until=timezone.now() + timedelta(days=5)
        )

        call_command('refresh_pro_statuses')

        expired_user.refresh_from_db()
        active_user.refresh_from_db()
        self.assertFalse(expired_user.is_pro)
        self.assertTrue(active_user.is_pro)


@unittest.skip("Auth is handled by Supabase; no Django password-reset endpoint.")
class PasswordResetTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_request_password_reset(self):
        """Test requesting password reset"""
        data = {'email': 'test@example.com'}
        response = self.client.post('/api/user/request-password-reset/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

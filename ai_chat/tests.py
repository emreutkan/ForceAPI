from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import ChatMessage, ChatSession
from .serializers import ChatMessageSerializer


User = get_user_model()


class AiChatTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='chat@example.com',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)

    def test_chat_message_serializer_exposes_timestamp_alias(self):
        session = ChatSession.objects.create(user=self.user, title='Test Session')
        message = ChatMessage.objects.create(
            session=session,
            role='ai',
            content='Hello from Force AI',
        )

        payload = ChatMessageSerializer(message).data

        self.assertIn('created_at', payload)
        self.assertIn('timestamp', payload)
        self.assertEqual(payload['timestamp'], payload['created_at'])

    @patch('ai_chat.views.get_chat_response', return_value='Focus on rows today.')
    @patch('ai_chat.views.build_user_context', return_value='Context')
    def test_message_endpoint_returns_timestamp(self, _mock_context, _mock_llm):
        session = ChatSession.objects.create(user=self.user, title='Coach')

        response = self.client.post(
            f'/api/chat/session/{session.id}/message/',
            {'message': 'What should I do next?'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('timestamp', response.data)
        self.assertEqual(response.data['timestamp'], response.data['created_at'])

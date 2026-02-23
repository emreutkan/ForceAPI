import logging

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer
from .llm import get_chat_response
from .prompts import FORCE_AI_SYSTEM_PROMPT
from .context import build_user_context

logger = logging.getLogger(__name__)


class ChatSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def message(self, request, pk=None):
        session = self.get_object()
        user_message = request.data.get('message')

        if not user_message:
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save user message
        ChatMessage.objects.create(session=session, role='user', content=user_message)

        # Build system prompt with user context
        user_context = build_user_context(request.user)
        system_content = FORCE_AI_SYSTEM_PROMPT + "\n\n" + user_context

        # Build conversation history for the LLM
        messages = [{'role': 'system', 'content': system_content}]

        history = list(session.messages.order_by('-created_at')[:20])
        history.reverse()  # back to chronological order for the LLM
        for msg in history:
            # Map our 'ai' role to the OpenAI-compatible 'assistant' role
            api_role = 'assistant' if msg.role == 'ai' else msg.role
            messages.append({'role': api_role, 'content': msg.content})

        # Call LLM
        try:
            ai_content = get_chat_response(messages)
        except Exception:
            return Response(
                {'error': 'Failed to get a response from the AI. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Save AI response
        ai_message = ChatMessage.objects.create(session=session, role='ai', content=ai_content)

        return Response(ChatMessageSerializer(ai_message).data)

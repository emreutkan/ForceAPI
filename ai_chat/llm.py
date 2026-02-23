import logging
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )
    return _client


def get_chat_response(conversation_messages):
    """
    Send conversation history to the LLM and return the response text.

    conversation_messages: list of dicts with 'role' and 'content' keys.
        role should be 'user', 'assistant', or 'system'.
    """
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=conversation_messages,
        )
        return response.choices[0].message.content
    except Exception:
        logger.exception("LLM call failed")
        raise

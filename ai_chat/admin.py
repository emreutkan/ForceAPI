from django.contrib import admin
from .models import ChatSession, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('role', 'content', 'created_at')


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'message_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'title')
    inlines = [ChatMessageInline]

    def message_count(self, obj):
        return obj.messages.count()

from django.contrib import admin

from .models import ChatChannel, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(ChatChannel)
class ChatChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "last_message_at", "created_at")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("channel", "sender", "content", "sent_at", "is_read")
    list_filter = ("is_read",)

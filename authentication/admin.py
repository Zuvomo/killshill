from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, LoginSession


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fieldsets = (
        ('Profile Information', {
            'fields': ('role', 'avatar', 'bio', 'location', 'website')
        }),
        ('Preferences', {
            'fields': ('email_notifications', 'push_notifications', 'newsletter_subscription')
        }),
        ('Account Status', {
            'fields': ('is_verified', 'is_premium', 'premium_expires_at')
        }),
        ('Social Accounts', {
            'fields': ('google_connected', 'twitter_connected', 'telegram_connected', 'telegram_id', 'telegram_username')
        }),
        ('Activity', {
            'fields': ('last_login_ip', 'login_count'),
            'classes': ('collapse',)
        }),
    )


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined', 'get_role')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined', 'userprofile__role')
    
    def get_role(self, obj):
        try:
            return obj.userprofile.role
        except UserProfile.DoesNotExist:
            return "No Profile"
    get_role.short_description = "Role"


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'ip_address', 'created_at', 'expires_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'ip_address', 'session_key']
    readonly_fields = ['session_key', 'user_agent', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

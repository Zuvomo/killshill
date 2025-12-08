from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'authentication'

urlpatterns = [
    # Web Views
    path('login/', views.LoginView.as_view(), name='login'),
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/<uidb64>/<token>/', views.ResetPasswordView.as_view(), name='reset_password'),
    
    # API Endpoints
    path('api/register/', views.api_register, name='api_register'),
    path('api/login/', views.api_login, name='api_login'),
    path('api/logout/', views.api_logout, name='api_logout'),
    path('api/profile/', views.api_profile, name='api_profile'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Telegram authentication
    path('telegram/callback/', views.telegram_login, name='telegram_login'),
    path('telegram/config/', views.get_telegram_config, name='telegram_config'),
    
    # Django Allauth URLs (for OAuth)
    path('accounts/', include('allauth.urls')),
]
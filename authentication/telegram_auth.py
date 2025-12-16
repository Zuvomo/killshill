"""
Telegram Login Widget Integration for Django
Custom implementation for Telegram authentication
"""

import hmac
import hashlib
import time
from urllib.parse import urlencode
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import UserProfile

class TelegramAuth:
    """
    Custom Telegram authentication handler
    """
    
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        self.bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
    
    def verify_telegram_auth(self, auth_data):
        """
        Verify the authentication data received from Telegram
        """
        if not self.bot_token:
            return False, "Telegram bot token not configured"
        
        # Check if data is recent (within 86400 seconds / 24 hours)
        auth_date = auth_data.get('auth_date')
        if not auth_date:
            return False, "Missing auth_date"
        
        try:
            auth_timestamp = int(auth_date)
            current_timestamp = int(time.time())
            if current_timestamp - auth_timestamp > 86400:  # 24 hours
                return False, "Authentication data is too old"
        except (ValueError, TypeError):
            return False, "Invalid auth_date format"
        
        # Create data string for hash verification
        hash_value = auth_data.pop('hash', None)
        if not hash_value:
            return False, "Missing hash"
        
        # Create data string
        data_check_arr = []
        for key, value in sorted(auth_data.items()):
            data_check_arr.append(f"{key}={value}")
        data_check_string = '\n'.join(data_check_arr)
        
        # Create secret key
        secret_key = hashlib.sha256(self.bot_token.encode()).digest()
        
        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, 
            data_check_string.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        # Verify hash
        if calculated_hash != hash_value:
            return False, "Hash verification failed"
        
        return True, "Authentication verified"
    
    def get_or_create_user(self, telegram_data):
        """
        Get or create user from Telegram data
        """
        telegram_id = telegram_data.get('id')
        if not telegram_id:
            return None, "Missing Telegram ID"
        
        # Check if user already exists with this Telegram ID
        try:
            profile = UserProfile.objects.get(telegram_id=telegram_id)
            return profile.user, "Existing user"
        except UserProfile.DoesNotExist:
            pass
        
        # Create new user
        username = telegram_data.get('username', f"telegram_user_{telegram_id}")
        first_name = telegram_data.get('first_name', '')
        last_name = telegram_data.get('last_name', '')
        
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        
        # Create user
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=''  # Telegram doesn't provide email
        )
        
        # Create or update profile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'telegram_id': telegram_id,
                'telegram_username': telegram_data.get('username', ''),
                'telegram_connected': True,
                'verified': True  # Telegram users are considered verified
            }
        )
        
        if not created:
            profile.telegram_id = telegram_id
            profile.telegram_username = telegram_data.get('username', '')
            profile.telegram_connected = True
            profile.save()
        
        return user, "New user created"

# Initialize telegram auth instance
telegram_auth = TelegramAuth()

@csrf_exempt
@require_POST
def telegram_login(request):
    """
    Handle Telegram login callback
    """
    try:
        # Get auth data from POST request
        auth_data = {}
        for key in ['id', 'auth_date', 'first_name', 'last_name', 'username', 'photo_url', 'hash']:
            value = request.POST.get(key)
            if value:
                auth_data[key] = value
        
        if not auth_data:
            return JsonResponse({
                'success': False,
                'error': 'No authentication data received'
            })
        
        # Verify authentication
        is_valid, message = telegram_auth.verify_telegram_auth(auth_data.copy())
        if not is_valid:
            return JsonResponse({
                'success': False,
                'error': f'Authentication failed: {message}'
            })
        
        # Get or create user
        user, user_status = telegram_auth.get_or_create_user(auth_data)
        if not user:
            return JsonResponse({
                'success': False,
                'error': f'User creation failed: {user_status}'
            })
        
        # Log user in
        login(request, user)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully logged in via Telegram ({user_status})',
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'redirect_url': '/dashboard/'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })

def get_telegram_login_widget_script(request):
    """
    Generate Telegram login widget script
    """
    # Check if Telegram is properly configured
    if not telegram_auth.bot_token:
        return JsonResponse({
            'success': False,
            'error': 'Telegram bot token not configured',
            'configured': False
        })
    
    if not telegram_auth.bot_username:
        return JsonResponse({
            'success': False,
            'error': 'Telegram bot username not configured',
            'configured': False
        })
    
    try:
        # Get current domain
        domain = request.get_host()
        protocol = 'https' if request.is_secure() else 'http'
        auth_url = f"{protocol}://{domain}/auth/telegram/callback/"
        
        # Validate domain is not localhost in production
        if domain.startswith('localhost') or domain.startswith('127.0.0.1'):
            return JsonResponse({
                'success': False,
                'error': 'Telegram login requires a public domain (not localhost)',
                'configured': True,
                'dev_note': 'For local development, use ngrok or similar tunneling service'
            })
        
        script_config = {
            'bot_username': telegram_auth.bot_username,
            'auth_url': auth_url,
            'request_access': 'write',
            'size': 'medium',
            'corner_radius': '8'
        }
        
        return JsonResponse({
            'success': True,
            'config': script_config,
            'configured': True
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Configuration error: {str(e)}',
            'configured': False
        })
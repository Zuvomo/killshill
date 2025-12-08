from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views import View
from django.http import JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from allauth.socialaccount.models import SocialAccount
from .models import UserProfile, LoginSession
from .telegram_auth import telegram_login, get_telegram_login_widget_script


class LoginView(View):
    """
    Traditional login view for email/password authentication
    """
    template_name = 'authentication/login.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return render(request, self.template_name)
    
    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember = request.POST.get('remember')
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if not email or not password:
                return JsonResponse({'success': False, 'error': 'Email and password are required'})
            
            try:
                user = User.objects.get(email=email)
                user = authenticate(request, username=user.username, password=password)
                
                if user:
                    login(request, user)
                    
                    # Handle remember me - set session expiry
                    if remember:
                        # Remember for 30 days
                        request.session.set_expiry(30 * 24 * 60 * 60)
                    else:
                        # Expire when browser closes
                        request.session.set_expiry(0)
                    
                    # Update profile login tracking
                    profile, created = UserProfile.objects.get_or_create(user=user)
                    profile.login_count += 1
                    profile.last_login_ip = self.get_client_ip(request)
                    profile.save()
                    
                    return JsonResponse({
                        'success': True, 
                        'redirect_url': reverse('dashboard:home'),
                        'message': 'Login successful!'
                    })
                else:
                    return JsonResponse({'success': False, 'error': 'Invalid credentials'})
            except User.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'User with this email does not exist'})
        
        # Handle regular form submissions
        if not email or not password:
            messages.error(request, 'Email and password are required')
            return render(request, self.template_name)
        
        try:
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
            
            if user:
                login(request, user)
                
                # Handle remember me - set session expiry
                if remember:
                    # Remember for 30 days
                    request.session.set_expiry(30 * 24 * 60 * 60)
                else:
                    # Expire when browser closes
                    request.session.set_expiry(0)
                
                # Update profile login tracking
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.login_count += 1
                profile.last_login_ip = self.get_client_ip(request)
                profile.save()
                
                return redirect('dashboard:home')
            else:
                messages.error(request, 'Invalid credentials')
        except User.DoesNotExist:
            messages.error(request, 'User with this email does not exist')
        
        return render(request, self.template_name)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SignupView(View):
    """
    User registration view
    """
    template_name = 'authentication/signup.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return render(request, self.template_name)
    
    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Validation
            if not email or not password:
                return JsonResponse({'success': False, 'error': 'Email and password are required'})
            
            if password != confirm_password:
                return JsonResponse({'success': False, 'error': 'Passwords do not match'})
            
            if len(password) < 8:
                return JsonResponse({'success': False, 'error': 'Password must be at least 8 characters long'})
            
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                return JsonResponse({'success': False, 'error': 'User with this email already exists'})
            
            # Create user
            username = email.split('@')[0]  # Use email prefix as username
            # Ensure username is unique
            counter = 1
            original_username = username
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            # Create user profile
            UserProfile.objects.create(
                user=user,
                verified=False,
                last_login_ip=self.get_client_ip(request)
            )
            
            return JsonResponse({
                'success': True, 
                'redirect_url': reverse('authentication:login'),
                'message': 'Account created successfully! Please log in.'
            })
        
        # Handle regular form submissions
        # Validation
        if not email or not password:
            messages.error(request, 'Email and password are required')
            return render(request, self.template_name)
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return render(request, self.template_name)
        
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long')
            return render(request, self.template_name)
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            messages.error(request, 'User with this email already exists')
            return render(request, self.template_name)
        
        # Create user
        username = email.split('@')[0]  # Use email prefix as username
        # Ensure username is unique
        counter = 1
        original_username = username
        while User.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        # Create user profile
        UserProfile.objects.create(
            user=user,
            verified=False,
            last_login_ip=self.get_client_ip(request)
        )
        
        messages.success(request, 'Account created successfully! Please log in.')
        return redirect('authentication:login')
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class LogoutView(View):
    """
    User logout view
    """
    def get(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully')
        return redirect('authentication:login')
    
    def post(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully')
        return redirect('authentication:login')


class ForgotPasswordView(View):
    """
    Password reset request view
    """
    template_name = 'authentication/forgot_password.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return render(request, self.template_name)
    
    def post(self, request):
        email = request.POST.get('email')
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if not email:
                return JsonResponse({'success': False, 'error': 'Email is required'})
            
            try:
                user = User.objects.get(email=email)
                
                # Generate reset token
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Build reset URL
                current_site = get_current_site(request)
                reset_url = request.build_absolute_uri(
                    reverse('authentication:reset_password', kwargs={'uidb64': uid, 'token': token})
                )
                
                # Send email
                subject = 'Password Reset Request - KillShill'
                message = f"""
                Hi {user.first_name or user.username},
                
                You have requested to reset your password for your KillShill account.
                
                Click the link below to reset your password:
                {reset_url}
                
                If you didn't request this password reset, please ignore this email.
                This link will expire in 24 hours.
                
                Best regards,
                KillShill Team
                """
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    return JsonResponse({
                        'success': True,
                        'message': 'Password reset link has been sent to your email address.'
                    })
                except Exception as e:
                    return JsonResponse({
                        'success': False,
                        'error': 'Unable to send email. Please try again later.'
                    })
                    
            except User.DoesNotExist:
                # Don't reveal if email exists or not for security
                return JsonResponse({
                    'success': True,
                    'message': 'If an account with this email exists, a password reset link has been sent.'
                })
        
        # Handle regular form submissions
        if not email:
            messages.error(request, 'Email is required')
            return render(request, self.template_name)
        
        try:
            user = User.objects.get(email=email)
            
            # Generate reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset URL
            current_site = get_current_site(request)
            reset_url = request.build_absolute_uri(
                reverse('authentication:reset_password', kwargs={'uidb64': uid, 'token': token})
            )
            
            # Send email
            subject = 'Password Reset Request - KillShill'
            message = f"""
            Hi {user.first_name or user.username},
            
            You have requested to reset your password for your KillShill account.
            
            Click the link below to reset your password:
            {reset_url}
            
            If you didn't request this password reset, please ignore this email.
            This link will expire in 24 hours.
            
            Best regards,
            KillShill Team
            """
            
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                messages.success(request, 'Password reset link has been sent to your email address.')
            except Exception as e:
                messages.error(request, 'Unable to send email. Please try again later.')
                
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            messages.success(request, 'If an account with this email exists, a password reset link has been sent.')
        
        return render(request, self.template_name)


class ResetPasswordView(View):
    """
    Password reset confirmation view
    """
    template_name = 'authentication/reset_password.html'
    
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
            
            if default_token_generator.check_token(user, token):
                # Store user ID in session for security
                request.session['reset_user_id'] = user.id
                return render(request, self.template_name)
            else:
                messages.error(request, 'Invalid or expired reset link')
                return redirect('authentication:forgot_password')
                
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            messages.error(request, 'Invalid reset link')
            return redirect('authentication:forgot_password')
    
    def post(self, request, uidb64, token):
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        # Get user from session
        user_id = request.session.get('reset_user_id')
        if not user_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Invalid session. Please request a new reset link.'})
            messages.error(request, 'Invalid session. Please request a new reset link.')
            return redirect('authentication:forgot_password')
        
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Invalid user. Please request a new reset link.'})
            messages.error(request, 'Invalid user. Please request a new reset link.')
            return redirect('authentication:forgot_password')
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if not password or not confirm_password:
                return JsonResponse({'success': False, 'error': 'All fields are required'})
            
            if password != confirm_password:
                return JsonResponse({'success': False, 'error': 'Passwords do not match'})
            
            if len(password) < 8:
                return JsonResponse({'success': False, 'error': 'Password must be at least 8 characters long'})
            
            # Reset password
            user.set_password(password)
            user.save()
            
            # Clear session
            if 'reset_user_id' in request.session:
                del request.session['reset_user_id']
            
            return JsonResponse({
                'success': True,
                'message': 'Password reset successfully! You can now log in with your new password.',
                'redirect_url': reverse('authentication:login')
            })
        
        # Handle regular form submissions
        if not password or not confirm_password:
            messages.error(request, 'All fields are required')
            return render(request, self.template_name)
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return render(request, self.template_name)
        
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long')
            return render(request, self.template_name)
        
        # Reset password
        user.set_password(password)
        user.save()
        
        # Clear session
        if 'reset_user_id' in request.session:
            del request.session['reset_user_id']
        
        messages.success(request, 'Password reset successfully! You can now log in with your new password.')
        return redirect('authentication:login')


# API Views for JWT Authentication

@api_view(['POST'])
@permission_classes([AllowAny])
def api_register(request):
    """
    API endpoint for user registration
    """
    email = request.data.get('email')
    password = request.data.get('password')
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')
    
    if not email or not password:
        return Response({
            'error': 'Email and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if User.objects.filter(email=email).exists():
        return Response({
            'error': 'User with this email already exists'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Create user
    username = email.split('@')[0]
    counter = 1
    original_username = username
    while User.objects.filter(username=username).exists():
        username = f"{original_username}{counter}"
        counter += 1
    
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name
    )
    
    # Create user profile
    UserProfile.objects.create(user=user, verified=False)
    
    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'message': 'User registered successfully',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        },
        'tokens': {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """
    API endpoint for login with JWT token generation
    """
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response({
            'error': 'Email and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(email=email)
        user = authenticate(username=user.username, password=password)
        
        if user:
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Update profile login tracking
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.login_count += 1
            profile.save()
            
            return Response({
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_verified': profile.is_verified,
                    'is_premium': profile.is_premium,
                    'role': profile.role,
                },
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                }
            })
        else:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except User.DoesNotExist:
        return Response({
            'error': 'User with this email does not exist'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_profile(request):
    """
    API endpoint to get user profile
    """
    try:
        profile = UserProfile.objects.get(user=request.user)
        return Response({
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
            },
            'profile': {
                'role': profile.role,
                'avatar': profile.avatar,
                'bio': profile.bio,
                'location': profile.location,
                'website': profile.website,
                'is_verified': profile.is_verified,
                'is_premium': profile.is_premium,
                'google_connected': profile.google_connected,
                'twitter_connected': profile.twitter_connected,
                'telegram_connected': profile.telegram_connected,
                'login_count': profile.login_count,
                'created_at': profile.created_at,
            }
        })
    except UserProfile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    """
    API endpoint for logout (blacklist refresh token)
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        return Response({'message': 'Successfully logged out'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def get_telegram_config(request):
    """
    Get Telegram login widget configuration
    """
    return get_telegram_login_widget_script(request)

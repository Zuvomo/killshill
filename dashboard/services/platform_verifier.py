"""
Platform Verification Service
Handles cross-platform verification of influencer accounts and data
"""

import requests
import re
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs
import time
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
import logging
from .apify_integration import apify_service

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of platform verification"""
    is_valid: bool
    actual_followers: Optional[int] = None
    actual_name: Optional[str] = None
    account_age_days: Optional[int] = None
    is_verified: bool = False
    engagement_rate: Optional[float] = None
    recent_activity: bool = True
    error_message: Optional[str] = None
    confidence_score: int = 0  # 0-100


class BasePlatformVerifier:
    """Base class for platform verifiers"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    async def verify(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify platform account - to be implemented by subclasses"""
        raise NotImplementedError
    
    def extract_username_from_url(self, url: str) -> Optional[str]:
        """Extract username from platform URL"""
        raise NotImplementedError
    
    def calculate_confidence_score(self, result: VerificationResult, submitted_data: Dict) -> int:
        """Calculate confidence score based on verification results"""
        score = 0
        
        if result.is_valid:
            score += 30
            
        # Follower count accuracy
        if result.actual_followers and submitted_data.get('follower_count'):
            submitted_count = int(submitted_data['follower_count'])
            actual_count = result.actual_followers
            
            # Allow 10% variance
            if abs(actual_count - submitted_count) / max(actual_count, submitted_count) <= 0.1:
                score += 25  # Exact match gets highest points
            elif abs(actual_count - submitted_count) / max(actual_count, submitted_count) <= 0.2:
                score += 15  # 20% variance
            elif abs(actual_count - submitted_count) / max(actual_count, submitted_count) <= 0.5:
                score += 5   # 50% variance
        
        # Account verification
        if result.is_verified:
            score += 15
            
        # Recent activity
        if result.recent_activity:
            score += 10
            
        # Account age (older accounts are generally more trustworthy)
        if result.account_age_days:
            if result.account_age_days > 365:
                score += 10
            elif result.account_age_days > 180:
                score += 5
                
        # Engagement rate (good engagement indicates active audience)
        if result.engagement_rate:
            if result.engagement_rate > 3.0:
                score += 10
            elif result.engagement_rate > 1.0:
                score += 5
        
        return min(score, 100)


class TwitterVerifier(BasePlatformVerifier):
    """Twitter account verifier using multiple methods"""
    
    def __init__(self):
        super().__init__()
        self.api_key = getattr(settings, 'TWITTER_API_KEY', None)
        self.api_secret = getattr(settings, 'TWITTER_API_SECRET', None)
        self.bearer_token = getattr(settings, 'TWITTER_BEARER_TOKEN', None)
    
    def extract_username_from_url(self, url: str) -> Optional[str]:
        """Extract Twitter username from URL"""
        patterns = [
            r'twitter\.com/([^/?\s]+)',
            r'x\.com/([^/?\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # Remove @ if present
                return username.lstrip('@')
        return None
    
    async def verify(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify Twitter account"""
        username = self.extract_username_from_url(url)
        if not username:
            return VerificationResult(
                is_valid=False,
                error_message="Invalid Twitter URL format"
            )
        
        cache_key = f"twitter_verify_{username}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # Try Twitter API v2 first (most reliable)
            if self.bearer_token:
                result = await self._verify_with_api_v2(username, submitted_data)
            else:
                # Fallback to web scraping
                result = await self._verify_with_scraping(username, submitted_data)
            
            # Cache result for 1 hour
            cache.set(cache_key, result, 3600)
            return result
            
        except Exception as e:
            logger.error(f"Twitter verification failed for {username}: {str(e)}")
            return VerificationResult(
                is_valid=False,
                error_message=f"Verification failed: {str(e)}"
            )
    
    async def _verify_with_api_v2(self, username: str, submitted_data: Dict) -> VerificationResult:
        """Verify using Twitter API v2"""
        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"https://api.twitter.com/2/users/by/username/{username}"
        params = {
            'user.fields': 'created_at,description,public_metrics,verified,verified_type'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    user_data = data.get('data', {})
                    
                    followers_count = user_data.get('public_metrics', {}).get('followers_count', 0)
                    created_at = user_data.get('created_at')
                    is_verified = user_data.get('verified', False) or user_data.get('verified_type') is not None
                    
                    # Calculate account age
                    account_age_days = None
                    if created_at:
                        from datetime import datetime
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        account_age_days = (datetime.now(created_date.tzinfo) - created_date).days
                    
                    result = VerificationResult(
                        is_valid=True,
                        actual_followers=followers_count,
                        actual_name=user_data.get('name'),
                        account_age_days=account_age_days,
                        is_verified=is_verified,
                        recent_activity=True  # Assume active if API returns data
                    )
                    
                    result.confidence_score = self.calculate_confidence_score(result, submitted_data)
                    return result
                else:
                    return VerificationResult(
                        is_valid=False,
                        error_message=f"API error: {response.status}"
                    )
    
    async def _verify_with_scraping(self, username: str, submitted_data: Dict) -> VerificationResult:
        """Fallback verification using web scraping"""
        # Note: This is a simplified example. Real implementation would need more sophisticated scraping
        # and respect rate limits and ToS
        
        url = f"https://twitter.com/{username}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Basic existence check
                        if "This account doesn't exist" in html or "User not found" in html:
                            return VerificationResult(
                                is_valid=False,
                                error_message="Account not found"
                            )
                        
                        return VerificationResult(
                            is_valid=True,
                            confidence_score=50  # Lower confidence for scraping
                        )
                    else:
                        return VerificationResult(
                            is_valid=False,
                            error_message="Account not accessible"
                        )
        except Exception as e:
            return VerificationResult(
                is_valid=False,
                error_message=f"Scraping failed: {str(e)}"
            )


class TelegramVerifier(BasePlatformVerifier):
    """Telegram channel verifier"""
    
    def extract_username_from_url(self, url: str) -> Optional[str]:
        """Extract Telegram channel name from URL"""
        patterns = [
            r't\.me/([^/?\s]+)',
            r'telegram\.me/([^/?\s]+)',
            r'telegram\.dog/([^/?\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    async def verify(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify Telegram channel"""
        channel = self.extract_username_from_url(url)
        if not channel:
            return VerificationResult(
                is_valid=False,
                error_message="Invalid Telegram URL format"
            )
        
        cache_key = f"telegram_verify_{channel}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # Use Telegram API if available, otherwise web scraping
            if hasattr(settings, 'TELEGRAM_BOT_TOKEN'):
                result = await self._verify_with_bot_api(channel, submitted_data)
            else:
                result = await self._verify_with_web_preview(channel, submitted_data)
            
            cache.set(cache_key, result, 3600)
            return result
            
        except Exception as e:
            logger.error(f"Telegram verification failed for {channel}: {str(e)}")
            return VerificationResult(
                is_valid=False,
                error_message=f"Verification failed: {str(e)}"
            )
    
    async def _verify_with_bot_api(self, channel: str, submitted_data: Dict) -> VerificationResult:
        """Verify using Telegram Bot API"""
        token = settings.TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/bot{token}/getChat"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={'chat_id': f'@{channel}'}) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('ok'):
                        chat = data.get('result', {})
                        
                        # Get member count
                        member_count = None
                        member_url = f"https://api.telegram.org/bot{token}/getChatMemberCount"
                        async with session.post(member_url, json={'chat_id': f'@{channel}'}) as member_response:
                            if member_response.status == 200:
                                member_data = await member_response.json()
                                if member_data.get('ok'):
                                    member_count = member_data.get('result')
                        
                        result = VerificationResult(
                            is_valid=True,
                            actual_followers=member_count,
                            actual_name=chat.get('title'),
                            recent_activity=True
                        )
                        
                        result.confidence_score = self.calculate_confidence_score(result, submitted_data)
                        return result
                
                return VerificationResult(
                    is_valid=False,
                    error_message="Channel not found or not accessible"
                )
    
    async def _verify_with_web_preview(self, channel: str, submitted_data: Dict) -> VerificationResult:
        """Verify using web preview"""
        url = f"https://t.me/{channel}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Basic existence check
                    if "tgme_page_title" in html:
                        return VerificationResult(
                            is_valid=True,
                            confidence_score=40  # Lower confidence for web scraping
                        )
                
                return VerificationResult(
                    is_valid=False,
                    error_message="Channel not found"
                )


class YouTubeVerifier(BasePlatformVerifier):
    """YouTube channel verifier"""
    
    def __init__(self):
        super().__init__()
        self.api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    
    def extract_username_from_url(self, url: str) -> Optional[str]:
        """Extract YouTube channel ID or username from URL"""
        patterns = [
            r'youtube\.com/channel/([^/?\s]+)',
            r'youtube\.com/c/([^/?\s]+)',
            r'youtube\.com/@([^/?\s]+)',
            r'youtube\.com/user/([^/?\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    async def verify(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify YouTube channel"""
        channel_identifier = self.extract_username_from_url(url)
        if not channel_identifier:
            return VerificationResult(
                is_valid=False,
                error_message="Invalid YouTube URL format"
            )
        
        cache_key = f"youtube_verify_{channel_identifier}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            if self.api_key:
                result = await self._verify_with_api(channel_identifier, submitted_data)
            else:
                result = await self._verify_with_scraping(url, submitted_data)
            
            cache.set(cache_key, result, 3600)
            return result
            
        except Exception as e:
            logger.error(f"YouTube verification failed for {channel_identifier}: {str(e)}")
            return VerificationResult(
                is_valid=False,
                error_message=f"Verification failed: {str(e)}"
            )
    
    async def _verify_with_api(self, channel_identifier: str, submitted_data: Dict) -> VerificationResult:
        """Verify using YouTube Data API"""
        # Determine if it's a channel ID, username, or handle
        if channel_identifier.startswith('@'):
            # Handle format
            search_url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                'part': 'snippet',
                'q': channel_identifier,
                'type': 'channel',
                'key': self.api_key,
                'maxResults': 1
            }
        else:
            # Direct channel lookup
            search_url = "https://www.googleapis.com/youtube/v3/channels"
            # Try as channel ID first, then as username
            if len(channel_identifier) == 24 and channel_identifier.startswith('UC'):
                params = {
                    'part': 'snippet,statistics',
                    'id': channel_identifier,
                    'key': self.api_key
                }
            else:
                params = {
                    'part': 'snippet,statistics',
                    'forUsername': channel_identifier,
                    'key': self.api_key
                }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('items'):
                        channel = data['items'][0]
                        snippet = channel.get('snippet', {})
                        statistics = channel.get('statistics', {})
                        
                        subscriber_count = statistics.get('subscriberCount')
                        if subscriber_count:
                            subscriber_count = int(subscriber_count)
                        
                        result = VerificationResult(
                            is_valid=True,
                            actual_followers=subscriber_count,
                            actual_name=snippet.get('title'),
                            recent_activity=True
                        )
                        
                        result.confidence_score = self.calculate_confidence_score(result, submitted_data)
                        return result
                
                return VerificationResult(
                    is_valid=False,
                    error_message="Channel not found"
                )
    
    async def _verify_with_scraping(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Fallback verification using web scraping"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Basic existence check
                    if '"channelMetadataRenderer"' in html:
                        return VerificationResult(
                            is_valid=True,
                            confidence_score=30  # Lower confidence
                        )
                
                return VerificationResult(
                    is_valid=False,
                    error_message="Channel not accessible"
                )


class TikTokVerifier(BasePlatformVerifier):
    """TikTok account verifier using Apify integration"""
    
    def extract_username_from_url(self, url: str) -> Optional[str]:
        """Extract TikTok username from URL"""
        patterns = [
            r'tiktok\.com/@([^/?\s]+)',
            r'tiktok\.com/([^/?\s@]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # Remove @ if present
                return username.lstrip('@')
        
        # If it's just a username
        if url.startswith('@'):
            return url[1:]
        
        # Check if it's just a plain username without URL
        if '/' not in url and '.' not in url:
            return url
        
        return None
    
    async def verify(self, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify TikTok account using Apify service"""
        username = self.extract_username_from_url(url)
        if not username:
            return VerificationResult(
                is_valid=False,
                error_message="Invalid TikTok URL format"
            )
        
        cache_key = f"tiktok_verify_{username}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # Use Apify service for verification
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def get_apify_result():
                return apify_service.verify_tiktok_profile(url)
            
            apify_result = await get_apify_result()
            
            if apify_result.get('success'):
                # Convert Apify result to VerificationResult
                result = VerificationResult(
                    is_valid=True,
                    actual_followers=apify_result.get('followers', 0),
                    actual_name=apify_result.get('display_name'),
                    is_verified=apify_result.get('verified', False),
                    recent_activity=True,
                    confidence_score=apify_result.get('confidence_score', 50)
                )
                
                # Enhance confidence score based on comparison with submitted data
                result.confidence_score = self.calculate_confidence_score(result, submitted_data)
                
                # Cache result for 1 hour
                cache.set(cache_key, result, 3600)
                return result
            else:
                return VerificationResult(
                    is_valid=False,
                    error_message=apify_result.get('error', 'TikTok verification failed')
                )
                
        except Exception as e:
            logger.error(f"TikTok verification failed for {username}: {str(e)}")
            return VerificationResult(
                is_valid=False,
                error_message=f"Verification failed: {str(e)}"
            )


class PlatformVerificationService:
    """Main service for platform verification"""
    
    def __init__(self):
        self.verifiers = {
            'Twitter': TwitterVerifier(),
            'Telegram': TelegramVerifier(),
            'YouTube': YouTubeVerifier(),
            'TikTok': TikTokVerifier(),
            # Add more platforms as needed
        }
    
    async def verify_platform(self, platform: str, url: str, submitted_data: Dict) -> VerificationResult:
        """Verify platform account"""
        verifier = self.verifiers.get(platform)
        if not verifier:
            return VerificationResult(
                is_valid=False,
                error_message=f"Platform {platform} not supported for verification"
            )
        
        return await verifier.verify(url, submitted_data)
    
    def get_supported_platforms(self) -> list:
        """Get list of supported platforms"""
        return list(self.verifiers.keys())


# Singleton instance
verification_service = PlatformVerificationService()
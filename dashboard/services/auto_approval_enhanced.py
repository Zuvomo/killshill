"""
Enhanced Auto-Approval Service for TikTok, Twitter, YouTube influencers
Integrates with Apify scrapers for automated verification and approval
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

from ..models import InfluencerSubmission
from .apify_integration import apify_service

MIN_SUBMISSION_FOLLOWERS = getattr(settings, 'SUBMISSION_MIN_FOLLOWERS', 1000)

logger = logging.getLogger(__name__)

class EnhancedAutoApprovalService:
    """Enhanced service for automatic influencer approval with platform verification"""
    
    SUPPORTED_PLATFORMS = ['tiktok', 'twitter', 'youtube', 'telegram']
    APPROVAL_CRITERIA = {
        platform: {
            'min_followers': MIN_SUBMISSION_FOLLOWERS,
            'min_posts': 0,
            'description': f'{MIN_SUBMISSION_FOLLOWERS}+ followers required for auto-approval'
        }
        for platform in SUPPORTED_PLATFORMS
    }
    
    def __init__(self):
        self.apify_service = apify_service
        self.min_followers = MIN_SUBMISSION_FOLLOWERS
    
    def process_submission(self, submission_data: Dict) -> Dict:
        """
        Process a single submission through the auto-approval pipeline
        
        Args:
            submission_data: Dict containing submission and verification data
            
        Returns:
            Dict containing processing results
        """
        try:
            platform = (submission_data.get('platform') or '').lower()
            url = submission_data.get('url')
            username = submission_data.get('username', '')
            submitted_by = submission_data.get('submitted_by')
            category = submission_data.get('category')
            channel_name = submission_data.get('channel_name') or submission_data.get('display_name') or username
            
            if not submitted_by:
                return {'success': False, 'error': 'Authenticated user is required for submissions.'}
            
            if not url or not channel_name or not category:
                return {'success': False, 'error': 'Channel name, category, and URL are required.'}
            
            if platform not in self.SUPPORTED_PLATFORMS:
                return {
                    'success': False,
                    'error': f"Platform '{platform}' is not supported for auto-approval"
                }
            
            display_name = submission_data.get('display_name') or channel_name
            bio = submission_data.get('bio', '')
            followers = self._coerce_int(submission_data.get('followers'))
            following = self._coerce_int(submission_data.get('following'))
            posts_count = self._coerce_int(submission_data.get('posts_count'))
            verified = bool(submission_data.get('verified', False))
            avatar_url = submission_data.get('avatar_url', '') or ''  # Ensure never None
            description = submission_data.get('description', '')
            author_name = submission_data.get('author_name', '')
            ip_address = submission_data.get('ip_address')
            user_agent = submission_data.get('user_agent', '')
            categories = submission_data.get('categories', [])
            
            logger.info(f"Processing submission: {display_name} on {platform}")
            
            manual_follower_count = self._coerce_int(submission_data.get('follower_count_manual'))
            is_mock_data = bool(submission_data.get('mock_data', False))
            verification_confident = followers > 0 and not is_mock_data
            
            if not verification_confident:
                # Determine specific reason based on verification failure
                if is_mock_data and followers == 0:
                    reason = submission_data.get('verification_error', 'Unable to verify profile - no recent activity detected')
                elif is_mock_data:
                    reason = 'Profile verification failed - submission queued for manual review'
                else:
                    reason = 'Unable to verify follower count - submission queued for manual review'
                    
                approval_result = {
                    'approved': False,
                    'reason': reason,
                    'criteria_met': False,
                    'details': {
                        'followers': {'required': self.min_followers, 'actual': followers, 'met': False},
                        'verification': {'mock_data': is_mock_data, 'reason': reason}
                    }
                }
                status = 'pending'
            else:
                approval_result = self._check_platform_criteria(platform, followers, posts_count)
                status = 'approved' if approval_result['approved'] else 'rejected'
            
            rejection_reason = ''
            if status == 'rejected':
                rejection_reason = approval_result.get('reason', 'Does not meet follower threshold')
            elif status == 'pending':
                rejection_reason = approval_result.get('reason', '')
            
            try:
                submission = InfluencerSubmission.objects.create(
                    submitted_by=submitted_by,
                    platform=platform,
                    channel_name=channel_name,
                    author_name=author_name,
                    url=url,
                    follower_count=followers,
                    category=category,
                    categories=categories,  # Store all selected categories
                    description=description,
                    username=username,
                    display_name=display_name,
                    bio=bio,
                    following=following,
                    posts_count=posts_count,
                    verified=verified,
                    avatar_url=avatar_url,
                    meets_criteria=approval_result['approved'],
                    extracted_at=time.time(),
                    mock_data=submission_data.get('mock_data', False),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status=status,
                    auto_approved=approval_result['approved'],
                    approval_score=self._calculate_score(platform, followers, posts_count, verified),
                    rejection_reason=rejection_reason
                )
                
                # If approved, add to main influencer database
                influencer_id = None
                if status == 'approved':
                    influencer_id = self._add_to_influencer_database(submission)
                
                message = 'Automatically approved!' if status == 'approved' else (rejection_reason or 'Submitted for manual review.')
                
                logger.info(
                    f"Created submission {submission.id}: {display_name} - {status.upper()}"
                )
                
                return {
                    'success': True,
                    'auto_approved': approval_result['approved'],
                    'submission_id': submission.id,
                    'approval_score': submission.approval_score,
                    'status': submission.status,
                    'message': message,
                    'criteria_details': approval_result.get('details', {}),
                    'reason': rejection_reason,
                    'influencer_id': influencer_id
                }
            
            except Exception as exc:
                logger.error(f"Failed to create submission: {exc}")
                logger.error(f"Submission data: platform={platform}, channel_name={channel_name}, category={category}")
                return {'success': False, 'error': f'Database error: {str(exc)}'}
        
        except Exception as exc:
            error_msg = f"Error processing submission: {exc}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def batch_process_pending(self, limit: int = 10) -> Dict:
        """
        Process multiple pending submissions in batch
        
        Args:
            limit: Maximum number of submissions to process
            
        Returns:
            Dict containing batch processing results
        """
        pending_submissions = InfluencerSubmission.objects.filter(
            status='pending'
        ).order_by('submitted_at')[:limit]
        
        results = {
            'processed': 0,
            'approved': 0,
            'deferred': 0,
            'failed': 0,
            'details': []
        }
        
        for submission in pending_submissions:
            result = self.process_submission(submission.id)
            results['processed'] += 1
            
            if result.get('success'):
                if result.get('status') == 'approved':
                    results['approved'] += 1
                elif result.get('status') == 'deferred':
                    results['deferred'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'submission_id': submission.id,
                'channel_name': submission.channel_name,
                'platform': submission.platform,
                'result': result
            })
        
        logger.info(f"Batch processed {results['processed']} submissions: "
                   f"{results['approved']} approved, {results['deferred']} deferred, {results['failed']} failed")
        
        return results
    
    def _verify_profile(self, submission: InfluencerSubmission) -> Dict:
        """Verify profile using Apify scrapers"""
        
        try:
            profile_url = submission.profile_url or submission.channel_name
            
            # Use Apify service to verify profile
            verification_result = self.apify_service.verify_profile(
                submission.platform, 
                profile_url
            )
            
            return verification_result
            
        except Exception as e:
            logger.error(f"Profile verification failed for {submission.channel_name}: {str(e)}")
            return {
                'success': False,
                'error': f"Verification failed: {str(e)}"
            }
    
    def _update_submission_data(self, submission: InfluencerSubmission, verification_data: Dict):
        """Update submission with verified profile data"""
        
        try:
            with transaction.atomic():
                # Update basic info
                if verification_data.get('display_name'):
                    submission.channel_name = verification_data['display_name']
                
                if verification_data.get('profile_url'):
                    submission.profile_url = verification_data['profile_url']
                
                # Update follower data
                submission.follower_count = verification_data.get('followers', 0)
                submission.following_count = verification_data.get('following', 0)
                submission.posts_count = verification_data.get('posts_count', 0)
                
                # Update verification status
                submission.is_verified = verification_data.get('verified', False)
                
                # Store additional metadata
                submission.verification_data = {
                    'bio': verification_data.get('bio', ''),
                    'avatar_url': verification_data.get('avatar_url', ''),
                    'extracted_at': verification_data.get('extracted_at'),
                    'meets_criteria': verification_data.get('meets_criteria', False),
                    'mock_data': verification_data.get('mock_data', False)
                }
                
                submission.data_extracted_at = timezone.now()
                submission.save()
                
                logger.info(f"Updated submission data for {submission.channel_name}: "
                           f"{submission.follower_count} followers, {submission.posts_count} posts")
                
        except Exception as e:
            logger.error(f"Failed to update submission data for {submission.channel_name}: {str(e)}")
            raise
    
    def _check_platform_criteria(self, platform: str, followers: int, posts_count: int) -> Dict:
        """Check if submission meets auto-approval criteria"""
        
        criteria = self.APPROVAL_CRITERIA.get(platform, {})
        
        if not criteria:
            return {
                'approved': False,
                'reason': f"No criteria defined for platform '{platform}'"
            }
        
        # Check follower count
        min_followers = criteria.get('min_followers', 0)
        
        if followers < min_followers:
            return {
                'approved': False,
                'reason': f"Requires at least {min_followers} followers (found {followers})",
                'criteria_met': False,
                'details': {
                    'followers': {'required': min_followers, 'actual': followers, 'met': False}
                }
            }
        
        # Check post count
        min_posts = criteria.get('min_posts', 0)
        
        if posts_count < min_posts:
            return {
                'approved': False,
                'reason': f"Insufficient posts: {posts_count} < {min_posts}",
                'criteria_met': False,
                'details': {
                    'followers': {'required': min_followers, 'actual': followers, 'met': True},
                    'posts': {'required': min_posts, 'actual': posts_count, 'met': False}
                }
            }
        
        # All criteria met
        return {
            'approved': True,
            'reason': "All auto-approval criteria met",
            'criteria_met': True,
            'details': {
                'followers': {'required': min_followers, 'actual': followers, 'met': True},
                'posts': {'required': min_posts, 'actual': posts_count, 'met': True}
            }
        }
    
    def _coerce_int(self, value) -> int:
        """Safe conversion helper for follower counts"""
        try:
            if value in (None, ''):
                return 0
            if isinstance(value, bool):
                return int(value)
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    
    def _platform_specific_checks(self, submission: InfluencerSubmission, verification_data: Dict) -> Dict:
        """Perform platform-specific additional checks"""
        
        platform = submission.platform
        
        if platform == 'twitter':
            # Check if account is not suspended or private
            if verification_data.get('protected', False):
                return {
                    'passed': False,
                    'reason': "Twitter account is private/protected"
                }
        
        elif platform == 'youtube':
            # Check if channel has recent activity
            if verification_data.get('posts_count', 0) == 0:
                return {
                    'passed': False,
                    'reason': "YouTube channel has no videos"
                }
        
        elif platform == 'tiktok':
            # Check if account exists and is accessible
            if not verification_data.get('profile_url'):
                return {
                    'passed': False,
                    'reason': "TikTok profile not accessible"
                }
        
        # Additional content quality checks could be added here
        # For example, checking if recent posts are trading-related
        
        return {'passed': True}
    
    def _approve_submission(self, submission: InfluencerSubmission, approval_result: Dict) -> Dict:
        """Approve the submission"""
        
        try:
            with transaction.atomic():
                submission.status = 'approved'
                submission.approved_at = timezone.now()
                submission.approval_score = self._calculate_approval_score(submission)
                submission.approval_notes = approval_result.get('reason', 'Auto-approved')
                submission.auto_approved = True
                submission.save()
                
                logger.info(f"Auto-approved submission: {submission.channel_name} on {submission.platform}")
                
                # Send notification if configured
                if getattr(settings, 'SEND_APPROVAL_NOTIFICATIONS', False):
                    self._send_approval_notification(submission)
                
                return {
                    'success': True,
                    'status': 'approved',
                    'submission_id': submission.id,
                    'channel_name': submission.channel_name,
                    'platform': submission.platform,
                    'approval_score': submission.approval_score,
                    'message': 'Submission auto-approved successfully'
                }
                
        except Exception as e:
            logger.error(f"Failed to approve submission {submission.id}: {str(e)}")
            return {
                'success': False,
                'error': f"Approval failed: {str(e)}"
            }
    
    def _defer_submission(self, submission: InfluencerSubmission, approval_result: Dict) -> Dict:
        """Defer submission for manual review"""
        
        try:
            submission.status = 'deferred'
            submission.deferred_at = timezone.now()
            submission.failure_reason = approval_result.get('reason', 'Did not meet auto-approval criteria')
            submission.approval_notes = f"Deferred: {approval_result.get('reason')}"
            submission.save()
            
            logger.info(f"Deferred submission for manual review: {submission.channel_name} - {approval_result.get('reason')}")
            
            return {
                'success': True,
                'status': 'deferred',
                'submission_id': submission.id,
                'channel_name': submission.channel_name,
                'platform': submission.platform,
                'reason': approval_result.get('reason'),
                'message': 'Submission deferred for manual review'
            }
            
        except Exception as e:
            logger.error(f"Failed to defer submission {submission.id}: {str(e)}")
            return {
                'success': False,
                'error': f"Deferral failed: {str(e)}"
            }
    
    def _reject_submission(self, submission: InfluencerSubmission, reason: str) -> Dict:
        """Reject the submission"""
        
        try:
            submission.status = 'rejected'
            submission.rejected_at = timezone.now()
            submission.failure_reason = reason
            submission.approval_notes = f"Rejected: {reason}"
            submission.save()
            
            logger.info(f"Rejected submission: {submission.channel_name} - {reason}")
            
            return {
                'success': True,
                'status': 'rejected',
                'submission_id': submission.id,
                'channel_name': submission.channel_name,
                'platform': submission.platform,
                'reason': reason,
                'message': 'Submission rejected'
            }
            
        except Exception as e:
            logger.error(f"Failed to reject submission {submission.id}: {str(e)}")
            return {
                'success': False,
                'error': f"Rejection failed: {str(e)}"
            }
    
    def _handle_verification_failure(self, submission: InfluencerSubmission, verification_result: Dict) -> Dict:
        """Handle cases where profile verification fails"""
        
        error_message = verification_result.get('error', 'Profile verification failed')
        
        # Check if it's a temporary failure or permanent
        if 'timeout' in error_message.lower() or 'api error' in error_message.lower():
            # Temporary failure - defer for retry
            submission.status = 'deferred'
            submission.failure_reason = f"Verification failed (will retry): {error_message}"
            submission.save()
            
            return {
                'success': True,
                'status': 'deferred',
                'submission_id': submission.id,
                'reason': error_message,
                'message': 'Verification failed - will retry later'
            }
        else:
            # Permanent failure - reject
            return self._reject_submission(submission, f"Profile verification failed: {error_message}")
    
    def _calculate_score(self, platform: str, followers: int, posts_count: int, verified: bool) -> float:
        """Calculate approval score based on various factors"""
        
        score = 50.0  # Base score
        
        # Platform-specific scoring
        platform_scores = {
            'youtube': 1.2,  # YouTube gets higher score
            'twitter': 1.1,
            'tiktok': 1.0
        }
        
        score *= platform_scores.get(platform, 1.0)
        
        # Follower count scoring
        if followers >= 100000:
            score += 30
        elif followers >= 50000:
            score += 20
        elif followers >= 25000:
            score += 15
        elif followers >= 10000:
            score += 10
        
        # Verification status bonus
        if verified:
            score += 10
        
        # Post count scoring
        if posts_count >= 100:
            score += 10
        elif posts_count >= 50:
            score += 5
        
        # Cap score at 100
        return min(score, 100.0)
    
    def _send_approval_notification(self, submission: InfluencerSubmission):
        """Send email notification about approval"""
        
        try:
            if hasattr(submission, 'user') and submission.user and submission.user.email:
                subject = f"Influencer Approved: {submission.channel_name}"
                message = f"""
                Your submitted influencer "{submission.channel_name}" on {submission.platform.title()} 
                has been automatically approved!
                
                Platform: {submission.platform.title()}
                Followers: {submission.follower_count:,}
                Approval Score: {submission.approval_score:.1f}
                
                You can now track their performance in your dashboard.
                """
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [submission.user.email],
                    fail_silently=True
                )
                
        except Exception as e:
            logger.error(f"Failed to send approval notification: {str(e)}")
    
    def get_approval_stats(self) -> Dict:
        """Get statistics about the auto-approval process"""
        
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        
        stats = {
            'today': {
                'total': InfluencerSubmission.objects.filter(submitted_at__date=today).count(),
                'approved': InfluencerSubmission.objects.filter(
                    approved_at__date=today, auto_approved=True
                ).count(),
                'deferred': InfluencerSubmission.objects.filter(
                    deferred_at__date=today
                ).count(),
                'pending': InfluencerSubmission.objects.filter(
                    status='pending', submitted_at__date=today
                ).count()
            },
            'week': {
                'total': InfluencerSubmission.objects.filter(submitted_at__gte=week_ago).count(),
                'approved': InfluencerSubmission.objects.filter(
                    approved_at__gte=week_ago, auto_approved=True
                ).count(),
                'deferred': InfluencerSubmission.objects.filter(
                    deferred_at__gte=week_ago
                ).count()
            },
            'by_platform': {}
        }
        
        # Platform-specific stats
        for platform in self.SUPPORTED_PLATFORMS:
            platform_stats = {
                'total': InfluencerSubmission.objects.filter(platform=platform).count(),
                'approved': InfluencerSubmission.objects.filter(
                    platform=platform, status='approved', auto_approved=True
                ).count(),
                'approval_rate': 0
            }
            
            if platform_stats['total'] > 0:
                platform_stats['approval_rate'] = (
                    platform_stats['approved'] / platform_stats['total'] * 100
                )
            
            stats['by_platform'][platform] = platform_stats
        
        return stats
    
    def _add_to_influencer_database(self, submission):
        """Add approved submission to main influencer database"""
        from influencers.models import Influencer
        from django.utils import timezone

        try:
            # Check if influencer already exists
            existing = Influencer.objects.filter(url=submission.url).first()
            if not existing:
                influencer = Influencer.objects.create(
                    channel_name=submission.channel_name,
                    author_name=submission.author_name or '',
                    url=submission.url,
                    platform=submission.platform,
                    follower_count=submission.follower_count or 0,
                    created_at=timezone.now()
                )
                logger.info(f"Created influencer record {influencer.influencer_id} for {submission.channel_name}")
                return influencer.influencer_id
            else:
                logger.info(f"Influencer already exists: {existing.influencer_id} for URL {submission.url}")
                return existing.influencer_id
        except Exception as e:
            logger.error(f"Error adding submission {submission.id} to influencer database: {e}")
            return None

# Singleton instance
enhanced_auto_approval_service = EnhancedAutoApprovalService()

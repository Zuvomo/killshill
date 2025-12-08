"""
Auto-Approval Service
Handles automatic approval of influencer submissions based on verification results
"""

import asyncio
import logging
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.conf import settings

from ..models import InfluencerSubmission
from influencers.models import Influencer
from .platform_verifier import verification_service, VerificationResult

logger = logging.getLogger(__name__)


class AutoApprovalService:
    """Service for automatic approval of influencer submissions"""
    
    # Minimum thresholds for auto-approval
    MIN_CONFIDENCE_SCORE = getattr(settings, 'AUTO_APPROVAL_MIN_CONFIDENCE', 70)
    MIN_FOLLOWERS = getattr(settings, 'AUTO_APPROVAL_MIN_FOLLOWERS', 1000)
    MAX_FOLLOWER_VARIANCE = getattr(settings, 'AUTO_APPROVAL_MAX_VARIANCE', 0.3)  # 30%
    
    # Risk assessment weights
    WEIGHTS = {
        'verification_confidence': 0.4,
        'follower_accuracy': 0.25,
        'account_age': 0.15,
        'platform_verification': 0.1,
        'engagement_quality': 0.1
    }
    
    def __init__(self):
        self.verification_service = verification_service
    
    async def process_submission(self, submission_id: int) -> Dict:
        """
        Process a submission for auto-approval
        
        Args:
            submission_id: ID of the InfluencerSubmission
            
        Returns:
            Dict with processing results
        """
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def get_submission():
            try:
                return InfluencerSubmission.objects.get(id=submission_id)
            except InfluencerSubmission.DoesNotExist:
                return None
        
        submission = await get_submission()
        if not submission:
            return {
                'success': False,
                'error': 'Submission not found'
            }
        
        if submission.status != 'pending':
            return {
                'success': False,
                'error': 'Submission is not pending'
            }
        
        try:
            # Step 1: Verify platform account
            verification_result = await self._verify_platform_account(submission)
            
            # Step 2: Calculate approval score
            approval_score = await self._calculate_approval_score(submission, verification_result)
            
            # Step 3: Make approval decision
            should_approve = self._should_auto_approve(submission, verification_result, approval_score)
            
            # Step 4: Update submission with results
            await self._update_submission_results(
                submission, 
                verification_result, 
                approval_score, 
                should_approve
            )
            
            # Step 5: If approved, create influencer record
            influencer = None
            if should_approve:
                influencer = await self._create_influencer_record(submission, verification_result)
            
            return {
                'success': True,
                'approved': should_approve,
                'approval_score': approval_score,
                'confidence_score': verification_result.confidence_score,
                'verification_result': {
                    'is_valid': verification_result.is_valid,
                    'actual_followers': verification_result.actual_followers,
                    'is_verified': verification_result.is_verified,
                    'error_message': verification_result.error_message
                },
                'influencer_id': influencer.influencer_id if influencer else None
            }
            
        except Exception as e:
            logger.error(f"Auto-approval failed for submission {submission_id}: {str(e)}")
            
            # Mark submission for manual review  
            from asgiref.sync import sync_to_async
            submission.approval_score = 0
            submission.rejection_reason = f"Auto-approval failed: {str(e)}"
            
            @sync_to_async
            def save_submission():
                submission.save()
            
            await save_submission()
            
            return {
                'success': False,
                'error': str(e),
                'requires_manual_review': True
            }
    
    async def _verify_platform_account(self, submission: InfluencerSubmission) -> VerificationResult:
        """Verify the platform account"""
        submitted_data = {
            'follower_count': submission.follower_count,
            'channel_name': submission.channel_name,
            'author_name': submission.author_name,
        }
        
        return await self.verification_service.verify_platform(
            submission.platform,
            submission.url,
            submitted_data
        )
    
    async def _calculate_approval_score(
        self, 
        submission: InfluencerSubmission, 
        verification: VerificationResult
    ) -> int:
        """
        Calculate comprehensive approval score (0-100)
        
        Factors considered:
        - Platform verification confidence
        - Follower count accuracy
        - Account age and credibility
        - Platform verification badges
        - Engagement quality indicators
        """
        score_components = {}
        
        # 1. Verification confidence (40% weight)
        verification_score = verification.confidence_score if verification.is_valid else 0
        score_components['verification_confidence'] = verification_score
        
        # 2. Follower accuracy (25% weight)
        follower_score = self._calculate_follower_accuracy_score(submission, verification)
        score_components['follower_accuracy'] = follower_score
        
        # 3. Account age (15% weight)
        age_score = self._calculate_account_age_score(verification)
        score_components['account_age'] = age_score
        
        # 4. Platform verification (10% weight)
        platform_verification_score = 100 if verification.is_verified else 50
        score_components['platform_verification'] = platform_verification_score
        
        # 5. Engagement quality (10% weight)
        engagement_score = self._calculate_engagement_score(verification)
        score_components['engagement_quality'] = engagement_score
        
        # Calculate weighted score
        total_score = sum(
            score_components[component] * self.WEIGHTS[component]
            for component in score_components
        )
        
        # Apply penalties for red flags
        total_score = await self._apply_risk_penalties(submission, verification, total_score)
        
        logger.info(f"Approval score calculation for {submission.channel_name}: "
                   f"Components: {score_components}, Final: {int(total_score)}")
        
        return min(int(total_score), 100)
    
    def _calculate_follower_accuracy_score(
        self, 
        submission: InfluencerSubmission, 
        verification: VerificationResult
    ) -> int:
        """Calculate score based on follower count accuracy"""
        if not verification.actual_followers or not submission.follower_count:
            return 30  # Neutral score if data unavailable
        
        actual = verification.actual_followers
        submitted = submission.follower_count
        
        if actual == 0 or submitted == 0:
            return 0
        
        variance = abs(actual - submitted) / max(actual, submitted)
        
        if variance <= 0.05:  # 5% or less variance
            return 100
        elif variance <= 0.10:  # 10% or less variance
            return 80
        elif variance <= 0.20:  # 20% or less variance
            return 60
        elif variance <= 0.30:  # 30% or less variance
            return 40
        elif variance <= 0.50:  # 50% or less variance
            return 20
        else:
            return 0  # More than 50% variance is suspicious
    
    def _calculate_account_age_score(self, verification: VerificationResult) -> int:
        """Calculate score based on account age"""
        if not verification.account_age_days:
            return 50  # Neutral score if unavailable
        
        age_days = verification.account_age_days
        
        if age_days >= 730:  # 2+ years
            return 100
        elif age_days >= 365:  # 1+ years
            return 80
        elif age_days >= 180:  # 6+ months
            return 60
        elif age_days >= 90:   # 3+ months
            return 40
        elif age_days >= 30:   # 1+ months
            return 20
        else:
            return 0  # Very new accounts are risky
    
    def _calculate_engagement_score(self, verification: VerificationResult) -> int:
        """Calculate score based on engagement metrics"""
        if not verification.engagement_rate:
            return 50  # Neutral if unavailable
        
        rate = verification.engagement_rate
        
        if rate >= 5.0:
            return 100
        elif rate >= 3.0:
            return 80
        elif rate >= 1.5:
            return 60
        elif rate >= 0.5:
            return 40
        else:
            return 20
    
    async def _apply_risk_penalties(
        self, 
        submission: InfluencerSubmission, 
        verification: VerificationResult, 
        base_score: float
    ) -> float:
        """Apply penalties for risk factors"""
        penalties = 0
        
        # Recent submission history (check for spam)
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def get_recent_submissions_count():
            try:
                return InfluencerSubmission.objects.filter(
                    submitted_by=submission.submitted_by,
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count()
            except Exception:
                return 0
        
        recent_submissions = await get_recent_submissions_count()
        
        if recent_submissions > 3:
            penalties += 20  # Potential spam
        
        # URL/domain reputation
        if self._is_suspicious_url(submission.url):
            penalties += 15
        
        # Inconsistent naming
        if self._has_naming_inconsistencies(submission, verification):
            penalties += 10
        
        # Account not found or inaccessible
        if not verification.is_valid:
            penalties += 30
        
        return max(base_score - penalties, 0)
    
    def _is_suspicious_url(self, url: str) -> bool:
        """Check if URL appears suspicious"""
        suspicious_indicators = [
            'bit.ly', 'tinyurl', 'goo.gl',  # Shortened URLs
            'suspicious-domain',  # Add known suspicious domains
        ]
        
        return any(indicator in url.lower() for indicator in suspicious_indicators)
    
    def _has_naming_inconsistencies(
        self, 
        submission: InfluencerSubmission, 
        verification: VerificationResult
    ) -> bool:
        """Check for naming inconsistencies"""
        if not verification.actual_name or not submission.channel_name:
            return False
        
        # Simple similarity check
        actual_lower = verification.actual_name.lower()
        submitted_lower = submission.channel_name.lower()
        
        # If names are completely different, flag as inconsistent
        return not (actual_lower in submitted_lower or submitted_lower in actual_lower)
    
    def _should_auto_approve(
        self, 
        submission: InfluencerSubmission, 
        verification: VerificationResult, 
        approval_score: int
    ) -> bool:
        """Determine if submission should be auto-approved"""
        
        # Basic requirements
        if not verification.is_valid:
            return False
        
        if approval_score < self.MIN_CONFIDENCE_SCORE:
            return False
        
        # Follower count requirements
        if verification.actual_followers and verification.actual_followers < self.MIN_FOLLOWERS:
            return False
        
        # Follower count variance check
        if (verification.actual_followers and submission.follower_count and
            submission.follower_count > 0):
            variance = abs(verification.actual_followers - submission.follower_count) / submission.follower_count
            if variance > self.MAX_FOLLOWER_VARIANCE:
                return False
        
        # Platform-specific requirements
        platform_checks = {
            'Twitter': lambda: verification.confidence_score >= 60,
            'Telegram': lambda: verification.confidence_score >= 50,
            'YouTube': lambda: verification.confidence_score >= 65,
            'TikTok': lambda: verification.confidence_score >= 60,
        }
        
        platform_check = platform_checks.get(submission.platform)
        if platform_check and not platform_check():
            return False
        
        return True
    
    async def _create_influencer_record(
        self,
        submission: InfluencerSubmission,
        verification: VerificationResult
    ) -> Influencer:
        """Create influencer record for approved submission"""
        from asgiref.sync import sync_to_async
        
        @sync_to_async
        def get_or_create_influencer():
            # Check if influencer already exists
            existing = Influencer.objects.filter(
                url=submission.url
            ).first()
            
            if existing:
                logger.info(f"Influencer already exists: {existing.influencer_id}")
                return existing
            
            # Create new influencer record
            influencer = Influencer.objects.create(
                channel_name=verification.actual_name or submission.channel_name,
                url=submission.url,
                platform=submission.platform,
                author_name=submission.author_name
            )
            
            logger.info(f"Created new influencer record: {influencer.influencer_id} for {submission.channel_name}")
            return influencer
        
        return await get_or_create_influencer()
    
    async def _update_submission_results(
        self,
        submission: InfluencerSubmission,
        verification: VerificationResult,
        approval_score: int,
        should_approve: bool
    ):
        """Update submission with verification and approval results"""
        from asgiref.sync import sync_to_async
        
        # Update submission fields
        submission.approval_score = approval_score
        
        if should_approve:
            submission.status = 'approved'
            submission.auto_approved = True
            submission.reviewed_at = timezone.now()
            logger.info(f"Auto-approved submission {submission.id}: {submission.channel_name}")
        else:
            # Keep as pending for manual review if score is reasonable, otherwise reject
            if approval_score < 40:
                submission.status = 'rejected'
                submission.rejection_reason = (
                    f"Failed verification checks. Approval score: {approval_score}. "
                    f"Verification confidence: {verification.confidence_score}."
                )
                submission.reviewed_at = timezone.now()
                logger.info(f"Auto-rejected submission {submission.id}: {submission.channel_name}")
            else:
                logger.info(f"Submission {submission.id} requires manual review. Score: {approval_score}")
        
        @sync_to_async
        def save_submission():
            submission.save()
        
        await save_submission()
    
    async def process_pending_submissions(self, limit: int = 10) -> Dict:
        """Process multiple pending submissions"""
        from asgiref.sync import sync_to_async
        
        # Get pending submissions using sync_to_async
        @sync_to_async
        def get_pending_submissions():
            return list(InfluencerSubmission.objects.filter(
                status='pending'
            ).order_by('created_at')[:limit])
        
        pending_submissions = await get_pending_submissions()
        results = []
        
        for submission in pending_submissions:
            try:
                result = await self.process_submission(submission.id)
                result['submission_id'] = submission.id
                result['channel_name'] = submission.channel_name
                results.append(result)
                
                # Rate limiting - wait between requests
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to process submission {submission.id}: {str(e)}")
                results.append({
                    'submission_id': submission.id,
                    'channel_name': submission.channel_name,
                    'success': False,
                    'error': str(e)
                })
        
        approved_count = sum(1 for r in results if r.get('approved'))
        rejected_count = sum(1 for r in results if r.get('success') and not r.get('approved'))
        
        return {
            'processed': len(results),
            'approved': approved_count,
            'rejected': rejected_count,
            'results': results
        }


# Singleton instance
auto_approval_service = AutoApprovalService()
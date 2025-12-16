"""
Celery tasks for auto-approval processing
"""

import asyncio
import logging
from typing import Dict, Optional
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

from .services.auto_approval import auto_approval_service
from .models import InfluencerSubmission

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_submission_auto_approval(self, submission_id: int) -> Dict:
    """
    Process single submission for auto-approval
    
    Args:
        submission_id: ID of the InfluencerSubmission
    
    Returns:
        Dict with processing results
    """
    try:
        logger.info(f"Starting auto-approval processing for submission {submission_id}")
        
        # Run async processing in sync context
        result = asyncio.run(auto_approval_service.process_submission(submission_id))
        
        # Send notification if configured
        if result.get('success'):
            try:
                submission = InfluencerSubmission.objects.get(id=submission_id)
                send_submission_notification.delay(submission_id, result.get('approved', False))
            except InfluencerSubmission.DoesNotExist:
                pass
        
        logger.info(f"Auto-approval completed for submission {submission_id}: {result}")
        return result
        
    except Exception as exc:
        logger.error(f"Auto-approval failed for submission {submission_id}: {str(exc)}")
        
        # Retry on temporary failures
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying auto-approval for submission {submission_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        
        # Mark for manual review after max retries
        try:
            submission = InfluencerSubmission.objects.get(id=submission_id)
            submission.approval_score = 0
            submission.rejection_reason = f"Auto-approval failed after {self.max_retries} attempts: {str(exc)}"
            submission.save()
        except InfluencerSubmission.DoesNotExist:
            pass
        
        return {
            'success': False,
            'error': str(exc),
            'max_retries_reached': True
        }


@shared_task
def process_batch_auto_approvals(limit: int = 20) -> Dict:
    """
    Process multiple pending submissions for auto-approval
    
    Args:
        limit: Maximum number of submissions to process
    
    Returns:
        Dict with batch processing results
    """
    try:
        logger.info(f"Starting batch auto-approval processing (limit: {limit})")
        
        result = asyncio.run(auto_approval_service.process_pending_submissions(limit))
        
        logger.info(f"Batch auto-approval completed: {result}")
        
        # Send summary notification if configured
        if getattr(settings, 'SEND_BATCH_NOTIFICATIONS', False):
            send_batch_summary_notification.delay(result)
        
        return result
        
    except Exception as exc:
        logger.error(f"Batch auto-approval failed: {str(exc)}")
        return {
            'success': False,
            'error': str(exc),
            'processed': 0,
            'approved': 0,
            'rejected': 0
        }


@shared_task
def send_submission_notification(submission_id: int, approved: bool):
    """
    Send notification about submission processing result
    
    Args:
        submission_id: ID of the processed submission
        approved: Whether the submission was approved
    """
    try:
        submission = InfluencerSubmission.objects.get(id=submission_id)
        
        # Email settings
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@killshill.com')
        
        if approved:
            subject = "🎉 Your Influencer Submission has been Approved!"
            message = f"""
Dear {submission.submitted_by.get_full_name() or submission.submitted_by.username},

Great news! Your influencer submission has been automatically approved and added to our platform.

Submission Details:
- Channel/Account: {submission.channel_name}
- Platform: {submission.platform}
- Followers: {submission.follower_count:,}
- Category: {submission.get_category_display()}

Your influencer is now part of the KillShill analytics platform and will be tracked for performance metrics.

Thank you for contributing to our community!

Best regards,
The KillShill Team
            """
        else:
            subject = "📋 Your Influencer Submission Requires Review"
            message = f"""
Dear {submission.submitted_by.get_full_name() or submission.submitted_by.username},

Thank you for your influencer submission. Our automated verification system has flagged your submission for manual review.

Submission Details:
- Channel/Account: {submission.channel_name}
- Platform: {submission.platform}
- Status: Pending Manual Review

This is not a rejection - our team will review your submission within 24-48 hours and provide feedback if needed.

Common reasons for manual review:
- Platform verification issues
- Large variance in follower counts
- New account (less than 30 days old)
- Incomplete profile information

Thank you for your patience!

Best regards,
The KillShill Team
            """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[submission.submitted_by.email],
            fail_silently=True
        )
        
        logger.info(f"Notification sent for submission {submission_id} (approved: {approved})")
        
    except InfluencerSubmission.DoesNotExist:
        logger.error(f"Cannot send notification - submission {submission_id} not found")
    except Exception as e:
        logger.error(f"Failed to send notification for submission {submission_id}: {str(e)}")


@shared_task
def send_batch_summary_notification(results: Dict):
    """
    Send summary notification about batch processing
    
    Args:
        results: Batch processing results
    """
    try:
        # Send to admin users
        admin_emails = list(
            User.objects.filter(is_staff=True, is_active=True)
            .values_list('email', flat=True)
        )
        
        if not admin_emails:
            return
        
        subject = "KillShill Auto-Approval Batch Summary"
        message = f"""
Auto-approval batch processing completed.

Summary:
- Processed: {results.get('processed', 0)}
- Approved: {results.get('approved', 0)}
- Rejected: {results.get('rejected', 0)}
- Pending Review: {results.get('processed', 0) - results.get('approved', 0) - results.get('rejected', 0)}

Detailed results available in the admin dashboard.

Best regards,
KillShill Auto-Approval System
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@killshill.com'),
            recipient_list=admin_emails,
            fail_silently=True
        )
        
        logger.info(f"Batch summary notification sent to {len(admin_emails)} admins")
        
    except Exception as e:
        logger.error(f"Failed to send batch summary notification: {str(e)}")


@shared_task
def schedule_auto_approval_batch():
    """
    Scheduled task to process pending submissions
    Run this periodically (e.g., every hour) via Celery Beat
    """
    logger.info("Running scheduled auto-approval batch")
    
    # Get current pending count
    pending_count = InfluencerSubmission.objects.filter(status='pending').count()
    
    if pending_count == 0:
        logger.info("No pending submissions to process")
        return {'message': 'No pending submissions'}
    
    # Process up to 50 submissions at a time
    limit = min(pending_count, 50)
    
    # Trigger batch processing
    result = process_batch_auto_approvals.delay(limit)
    
    return {
        'message': f'Scheduled batch processing of {limit} submissions',
        'task_id': result.id
    }


# Periodic task for cleanup (optional)
@shared_task
def cleanup_old_rejections():
    """
    Clean up old rejected submissions (optional maintenance task)
    Run this weekly to keep database clean
    """
    from datetime import timedelta
    from django.utils import timezone
    
    cutoff_date = timezone.now() - timedelta(days=90)  # 90 days old
    
    old_rejections = InfluencerSubmission.objects.filter(
        status='rejected',
        updated_at__lt=cutoff_date
    )
    
    count = old_rejections.count()
    
    if count > 0:
        old_rejections.delete()
        logger.info(f"Cleaned up {count} old rejected submissions")
        
        return {'cleaned_up': count}
    
    return {'cleaned_up': 0}
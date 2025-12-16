"""
Django signals for auto-approval workflow
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from .models import InfluencerSubmission

logger = logging.getLogger(__name__)


@receiver(post_save, sender=InfluencerSubmission)
def trigger_auto_approval(sender, instance, created, **kwargs):
    """
    Trigger auto-approval process when a new submission is created
    
    Args:
        sender: InfluencerSubmission model class
        instance: The InfluencerSubmission instance
        created: True if this is a new submission
    """
    
    # Only process new submissions that are pending
    if not created or instance.status != 'pending':
        return
    
    # Check if auto-approval is enabled
    if not getattr(settings, 'ENABLE_AUTO_APPROVAL', True):
        logger.info(f"Auto-approval disabled - submission {instance.id} will remain pending")
        return
    
    logger.info(f"New submission created - triggering auto-approval for {instance.id}")
    
    try:
        # Import here to avoid circular imports
        from .tasks import process_submission_auto_approval
        
        # Delay auto-approval by a few seconds to ensure transaction is committed
        process_submission_auto_approval.apply_async(
            args=[instance.id],
            countdown=5  # Wait 5 seconds
        )
        
        logger.info(f"Auto-approval task queued for submission {instance.id}")
        
    except ImportError:
        # Fallback if Celery is not available - queue for later processing
        logger.warning("Celery not available - submission will be processed manually or via management command")
        logger.info(f"Submission {instance.id} queued for manual processing. Run: python manage.py process_auto_approvals")
            
    except Exception as e:
        logger.error(f"Failed to queue auto-approval for submission {instance.id}: {str(e)}")


@receiver(post_save, sender=InfluencerSubmission)
def log_submission_status_change(sender, instance, created, **kwargs):
    """
    Log submission status changes for auditing
    
    Args:
        sender: InfluencerSubmission model class
        instance: The InfluencerSubmission instance
        created: True if this is a new submission
    """
    
    if created:
        logger.info(
            f"New influencer submission created: ID={instance.id}, "
            f"Channel={instance.channel_name}, Platform={instance.platform}, "
            f"Submitted by={instance.submitted_by.username}"
        )
    else:
        # Log status changes
        logger.info(
            f"Submission {instance.id} updated: Status={instance.status}, "
            f"Auto-approved={instance.auto_approved}, Score={instance.approval_score}"
        )
        
        # Log approval/rejection details
        if instance.status == 'approved' and instance.auto_approved:
            logger.info(
                f"Submission {instance.id} auto-approved: {instance.channel_name} "
                f"({instance.platform}) with score {instance.approval_score}"
            )
        elif instance.status == 'rejected':
            logger.info(
                f"Submission {instance.id} rejected: {instance.channel_name} "
                f"({instance.platform}) - Reason: {instance.rejection_reason[:100]}..."
            )
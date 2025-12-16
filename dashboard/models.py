from django.db import models
from django.contrib.auth.models import User
from influencers.models import Influencer, TradeCall


class InfluencerSubmission(models.Model):
    """
    Model to track influencer submissions from users
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PLATFORM_CHOICES = [
        ('tiktok', 'TikTok'),
        ('twitter', 'Twitter'),
        ('youtube', 'YouTube'),
        ('telegram', 'Telegram'),
    ]
    
    CATEGORY_CHOICES = [
        ('crypto', 'Cryptocurrency'),
        ('stocks', 'Stocks'),
        ('forex', 'Forex'),
    ]
    
    
    # Submission details
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='influencer_submissions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status and approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    auto_approved = models.BooleanField(default=False)
    approval_score = models.IntegerField(default=0, help_text="Auto-approval score calculated")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_submissions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, help_text="Reason for rejection if applicable")
    
    # Influencer information
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    channel_name = models.CharField(max_length=255, help_text="Channel/Account name")
    author_name = models.CharField(max_length=255, blank=True, help_text="Real name if known")
    url = models.URLField(help_text="Profile URL")
    follower_count = models.PositiveIntegerField(default=0, help_text="Number of followers/subscribers")
    manual_follower_count = models.PositiveIntegerField(default=0, help_text="User provided follower snapshot")
    
    # Categorization
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, blank=True, help_text="Primary category (for backward compatibility)")
    categories = models.JSONField(default=list, help_text="Multiple categories supported: crypto, stocks, forex")
    
    # Additional information
    description = models.TextField(blank=True, help_text="Background and description")
    
    # Platform verification data
    username = models.CharField(max_length=255, blank=True, help_text="Platform username")
    display_name = models.CharField(max_length=255, blank=True, help_text="Display name from platform")
    bio = models.TextField(blank=True, help_text="Profile bio from platform")
    following = models.PositiveIntegerField(default=0, help_text="Number of accounts following")
    posts_count = models.PositiveIntegerField(default=0, help_text="Number of posts/videos")
    verified = models.BooleanField(default=False, help_text="Platform verified status")
    avatar_url = models.URLField(max_length=500, blank=True, help_text="Profile avatar URL")
    meets_criteria = models.BooleanField(default=False, help_text="Meets auto-approval criteria")
    extracted_at = models.FloatField(null=True, blank=True, help_text="Timestamp when data was extracted")
    mock_data = models.BooleanField(default=False, help_text="Whether data is mocked")
    
    # Meta information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        db_table = 'influencer_submission'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['submitted_by', 'status']),
            models.Index(fields=['auto_approved']),
        ]
    
    def __str__(self):
        return f"{self.channel_name} ({self.platform}) - {self.get_status_display()}"
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_rejected(self):
        return self.status == 'rejected'
    
    def approve(self, reviewed_by=None):
        """Mark submission as approved"""
        from django.utils import timezone
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save()
    
    def reject(self, reason="", reviewed_by=None):
        """Mark submission as rejected"""
        from django.utils import timezone
        self.status = 'rejected'
        self.rejection_reason = reason
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save()


class AbuseReport(models.Model):
    """
    Model to track abuse reports for trade calls and influencer profiles
    """
    REPORT_TYPE_CHOICES = [
        ('call', 'Trade Call'),
        ('profile', 'Influencer Profile'),
    ]

    REASON_CHOICES = [
        ('fake_data', 'Fake or Manipulated Data'),
        ('spam', 'Spam or Promotional Content'),
        ('manipulation', 'Market Manipulation'),
        ('misleading', 'Misleading Information'),
        ('duplicate', 'Duplicate Profile'),
        ('offensive', 'Offensive Content'),
        ('scam', 'Potential Scam'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('reviewing', 'Under Review'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    # Report details
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='abuse_reports')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    description = models.TextField(help_text="Detailed description of the issue")

    # Related objects (nullable - one will be filled based on report_type)
    # db_constraint=False because Influencer and TradeCall are unmanaged models
    influencer = models.ForeignKey(Influencer, on_delete=models.CASCADE, null=True, blank=True, related_name='abuse_reports', db_constraint=False)
    trade_call = models.ForeignKey(TradeCall, on_delete=models.CASCADE, null=True, blank=True, related_name='abuse_reports', db_constraint=False)

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, help_text="Admin notes on resolution")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Meta
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'abuse_report'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['report_type', 'status']),
            models.Index(fields=['reporter']),
        ]

    def __str__(self):
        if self.report_type == 'call' and self.trade_call:
            return f"Report on Call #{self.trade_call.id} - {self.get_reason_display()}"
        elif self.report_type == 'profile' and self.influencer:
            return f"Report on {self.influencer.channel_name} - {self.get_reason_display()}"
        return f"Report #{self.id} - {self.get_reason_display()}"

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_resolved(self):
        return self.status == 'resolved'

    def resolve(self, resolution_notes="", reviewed_by=None):
        """Mark report as resolved"""
        from django.utils import timezone
        self.status = 'resolved'
        self.resolution_notes = resolution_notes
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save()

    def dismiss(self, resolution_notes="", reviewed_by=None):
        """Mark report as dismissed"""
        from django.utils import timezone
        self.status = 'dismissed'
        self.resolution_notes = resolution_notes
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save()


class Watchlist(models.Model):
    """
    Model for users to save/watchlist influencers they want to follow
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='watchlist')
    # db_constraint=False because Influencer is an unmanaged model
    influencer = models.ForeignKey(Influencer, on_delete=models.CASCADE, related_name='watched_by', db_constraint=False)
    added_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text="Personal notes about this influencer")

    class Meta:
        db_table = 'watchlist'
        unique_together = ('user', 'influencer')
        ordering = ['-added_at']
        indexes = [
            models.Index(fields=['user', 'added_at']),
        ]

    def __str__(self):
        return f"{self.user.username} watching {self.influencer.channel_name}"


class NotificationRead(models.Model):
    """
    Model to track which notifications have been read by users
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='read_notifications')
    notification_type = models.CharField(max_length=50, help_text="Type of notification: 'call' or 'submission'")
    notification_id = models.CharField(max_length=255, help_text="Unique identifier for the notification")
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notification_read'
        unique_together = ('user', 'notification_id')
        ordering = ['-read_at']
        indexes = [
            models.Index(fields=['user', 'notification_type']),
            models.Index(fields=['user', 'notification_id']),
        ]
    
    def __str__(self):
        return f"{self.user.username} read {self.notification_type}:{self.notification_id}"

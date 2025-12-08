from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import asyncio

from .models import InfluencerSubmission, AbuseReport, Watchlist


@admin.register(InfluencerSubmission)
class InfluencerSubmissionAdmin(admin.ModelAdmin):
    """
    Enhanced admin interface for InfluencerSubmission with auto-approval features
    """
    list_display = [
        'channel_name', 'platform', 'status_display', 'follower_count', 
        'approval_score_display', 'auto_approved', 'submitted_by', 'created_at',
        'verification_actions'
    ]
    list_filter = [
        'status', 'platform', 'category', 'auto_approved', 
        'created_at', 'approval_score'
    ]
    search_fields = [
        'channel_name', 'author_name', 'url', 'description',
        'submitted_by__username', 'submitted_by__email'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'ip_address', 'user_agent',
        'approval_score', 'auto_approved'
    ]
    fieldsets = [
        ('Submission Info', {
            'fields': ['submitted_by', 'created_at', 'updated_at', 'status']
        }),
        ('Influencer Details', {
            'fields': ['platform', 'channel_name', 'author_name', 'url', 'follower_count']
        }),
        ('Classification', {
            'fields': ['category', 'categories']
        }),
        ('Content', {
            'fields': ['description']
        }),
        ('Auto-Approval Results', {
            'fields': ['auto_approved', 'approval_score', 'reviewed_by', 'reviewed_at', 'rejection_reason'],
            'classes': ['wide']
        }),
        ('Technical', {
            'fields': ['ip_address', 'user_agent'],
            'classes': ['collapse']
        })
    ]
    actions = ['approve_submissions', 'reject_submissions', 'trigger_auto_approval', 'export_to_csv']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:submission_id>/verify/',
                self.admin_site.admin_view(self.verify_submission),
                name='dashboard_verify_submission',
            ),
            path(
                '<int:submission_id>/auto-approve/',
                self.admin_site.admin_view(self.manual_auto_approve),
                name='dashboard_auto_approve_submission',
            ),
        ]
        return custom_urls + urls
    
    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'pending': '#ffa500',  # Orange
            'approved': '#28a745',  # Green
            'rejected': '#dc3545',  # Red
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#000'),
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def approval_score_display(self, obj):
        """Display approval score with color coding"""
        if obj.approval_score is None:
            return format_html('<span style="color: #6c757d;">N/A</span>')
        
        color = '#28a745' if obj.approval_score >= 70 else '#ffa500' if obj.approval_score >= 40 else '#dc3545'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.approval_score
        )
    approval_score_display.short_description = 'Score'
    
    def verification_actions(self, obj):
        """Display verification action buttons"""
        if obj.status == 'pending':
            return format_html(
                '<a href="/admin/dashboard/influencersubmission/{}/verify/" class="button" '
                'style="background: #007cba; color: white; padding: 3px 8px; text-decoration: none; '
                'border-radius: 3px; font-size: 11px; margin: 1px;">Verify</a> '
                '<a href="/admin/dashboard/influencersubmission/{}/auto-approve/" class="button" '
                'style="background: #28a745; color: white; padding: 3px 8px; text-decoration: none; '
                'border-radius: 3px; font-size: 11px; margin: 1px;">Auto-Approve</a>',
                obj.id, obj.id
            )
        return format_html('<span style="color: #6c757d;">N/A</span>')
    verification_actions.short_description = 'Actions'
    
    def verify_submission(self, request, submission_id):
        """AJAX endpoint to verify single submission"""
        submission = get_object_or_404(InfluencerSubmission, id=submission_id)
        
        try:
            from .services.auto_approval import auto_approval_service
            from .services.platform_verifier import verification_service
            
            # Get verification result only (don't approve yet)
            submitted_data = {
                'follower_count': submission.follower_count,
                'channel_name': submission.channel_name,
                'author_name': submission.author_name,
            }
            
            verification_result = asyncio.run(
                verification_service.verify_platform(
                    submission.platform,
                    submission.url,
                    submitted_data
                )
            )
            
            return JsonResponse({
                'success': True,
                'verification': {
                    'is_valid': verification_result.is_valid,
                    'actual_followers': verification_result.actual_followers,
                    'actual_name': verification_result.actual_name,
                    'is_verified': verification_result.is_verified,
                    'confidence_score': verification_result.confidence_score,
                    'account_age_days': verification_result.account_age_days,
                    'engagement_rate': verification_result.engagement_rate,
                    'error_message': verification_result.error_message
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    def manual_auto_approve(self, request, submission_id):
        """AJAX endpoint to manually trigger auto-approval"""
        submission = get_object_or_404(InfluencerSubmission, id=submission_id)
        
        try:
            from .services.auto_approval import auto_approval_service
            
            result = asyncio.run(auto_approval_service.process_submission(submission_id))
            
            return JsonResponse({
                'success': True,
                'result': result
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    def trigger_auto_approval(self, request, queryset):
        """Bulk trigger auto-approval for selected submissions"""
        pending_submissions = queryset.filter(status='pending')
        count = pending_submissions.count()
        
        if count == 0:
            self.message_user(request, "No pending submissions selected.")
            return
        
        # Queue auto-approval tasks
        try:
            from .tasks import process_submission_auto_approval
            
            for submission in pending_submissions:
                process_submission_auto_approval.delay(submission.id)
            
            self.message_user(
                request, 
                f'Auto-approval queued for {count} submissions. Check back in a few minutes.'
            )
            
        except ImportError:
            # Fallback without Celery
            from .services.auto_approval import auto_approval_service
            
            processed = 0
            approved = 0
            
            for submission in pending_submissions[:10]:  # Limit to 10 for sync processing
                try:
                    result = asyncio.run(auto_approval_service.process_submission(submission.id))
                    processed += 1
                    if result.get('approved'):
                        approved += 1
                except Exception as e:
                    continue
            
            self.message_user(
                request,
                f'Processed {processed} submissions synchronously. {approved} approved.'
            )
    
    trigger_auto_approval.short_description = "Trigger auto-approval for selected submissions"
    
    def export_to_csv(self, request, queryset):
        """Export submissions to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="influencer_submissions.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Channel Name', 'Platform', 'Status', 'Auto Approved', 
            'Approval Score', 'Follower Count', 'URL', 'Category', 
            'Submitted By', 'Created At', 'Reviewed At'
        ])
        
        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.channel_name,
                obj.platform,
                obj.status,
                obj.auto_approved,
                obj.approval_score or '',
                obj.follower_count,
                obj.url,
                obj.category,
                obj.submitted_by.username,
                obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                obj.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if obj.reviewed_at else ''
            ])
        
        return response
    
    export_to_csv.short_description = "Export selected submissions to CSV"
    
    actions = ['approve_submissions', 'reject_submissions', 'trigger_auto_approval', 'export_to_csv']
    
    def approve_submissions(self, request, queryset):
        """Bulk approve submissions"""
        from django.utils import timezone
        
        updated = queryset.filter(status='pending').update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        
        self.message_user(request, f'Approved {updated} submissions.')
        
        # Add approved influencers to main database
        for submission in queryset.filter(status='approved'):
            self._add_to_main_database(submission)
    
    approve_submissions.short_description = "Approve selected submissions"
    
    def reject_submissions(self, request, queryset):
        """Bulk reject submissions"""
        from django.utils import timezone
        
        updated = queryset.filter(status='pending').update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason='Rejected by admin'
        )
        
        self.message_user(request, f'Rejected {updated} submissions.')
    
    reject_submissions.short_description = "Reject selected submissions"
    
    def _add_to_main_database(self, submission):
        """Add approved submission to main influencer database"""
        from influencers.models import Influencer
        
        try:
            # Check if already exists
            existing = Influencer.objects.filter(url=submission.url).first()
            if not existing:
                Influencer.objects.create(
                    channel_name=submission.channel_name,
                    author_name=submission.author_name,
                    url=submission.url,
                    platform=submission.platform
                )
        except Exception as e:
            print(f"Error adding to main database: {e}")
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'submitted_by', 'reviewed_by'
        )


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    """
    Admin interface for abuse reports with status management
    """
    list_display = [
        'id', 'report_type_display', 'reason_display', 'reporter',
        'subject_display', 'status_display', 'created_at', 'action_buttons'
    ]
    list_filter = [
        'status', 'report_type', 'reason', 'created_at'
    ]
    search_fields = [
        'description', 'reporter__username', 'resolution_notes',
        'influencer__channel_name', 'trade_call__id'
    ]
    readonly_fields = [
        'reporter', 'report_type', 'reason', 'description',
        'influencer', 'trade_call', 'created_at', 'updated_at', 'ip_address'
    ]
    fieldsets = [
        ('Report Details', {
            'fields': ['reporter', 'report_type', 'reason', 'description', 'ip_address']
        }),
        ('Subject', {
            'fields': ['influencer', 'trade_call']
        }),
        ('Status & Resolution', {
            'fields': ['status', 'reviewed_by', 'reviewed_at', 'resolution_notes']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]
    actions = ['mark_as_resolved', 'mark_as_dismissed', 'mark_as_reviewing']
    date_hierarchy = 'created_at'

    def report_type_display(self, obj):
        """Display report type with icon"""
        icons = {
            'call': '📊',
            'profile': '👤'
        }
        return format_html(
            '{} {}',
            icons.get(obj.report_type, ''),
            obj.get_report_type_display()
        )
    report_type_display.short_description = 'Type'

    def reason_display(self, obj):
        """Display reason with color coding"""
        colors = {
            'fake_data': '#dc3545',
            'scam': '#dc3545',
            'manipulation': '#ff6b6b',
            'spam': '#ffa500',
            'misleading': '#ffc107',
            'duplicate': '#17a2b8',
            'offensive': '#e83e8c',
            'other': '#6c757d'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.reason, '#000'),
            obj.get_reason_display()
        )
    reason_display.short_description = 'Reason'

    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'pending': '#ffa500',
            'reviewing': '#17a2b8',
            'resolved': '#28a745',
            'dismissed': '#6c757d'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#000'),
            obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def subject_display(self, obj):
        """Display the subject of the report"""
        if obj.report_type == 'call' and obj.trade_call:
            return format_html(
                '<a href="/dashboard/signals/{}/" target="_blank">Call #{}</a>',
                obj.trade_call.id, obj.trade_call.id
            )
        elif obj.report_type == 'profile' and obj.influencer:
            return format_html(
                '{} (@{})',
                obj.influencer.channel_name,
                obj.influencer.platform
            )
        return 'N/A'
    subject_display.short_description = 'Subject'

    def action_buttons(self, obj):
        """Display action buttons for pending reports"""
        if obj.status == 'pending':
            return format_html(
                '<a href="#" class="button" style="background: #28a745; color: white; '
                'padding: 3px 8px; text-decoration: none; border-radius: 3px; '
                'font-size: 11px; margin: 1px;">Resolve</a> '
                '<a href="#" class="button" style="background: #6c757d; color: white; '
                'padding: 3px 8px; text-decoration: none; border-radius: 3px; '
                'font-size: 11px; margin: 1px;">Dismiss</a>'
            )
        return '-'
    action_buttons.short_description = 'Actions'

    def mark_as_resolved(self, request, queryset):
        """Bulk mark reports as resolved"""
        from django.utils import timezone
        updated = queryset.filter(status__in=['pending', 'reviewing']).update(
            status='resolved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'Marked {updated} reports as resolved.')
    mark_as_resolved.short_description = "Mark as resolved"

    def mark_as_dismissed(self, request, queryset):
        """Bulk mark reports as dismissed"""
        from django.utils import timezone
        updated = queryset.filter(status__in=['pending', 'reviewing']).update(
            status='dismissed',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'Dismissed {updated} reports.')
    mark_as_dismissed.short_description = "Mark as dismissed"

    def mark_as_reviewing(self, request, queryset):
        """Bulk mark reports as under review"""
        updated = queryset.filter(status='pending').update(status='reviewing')
        self.message_user(request, f'Marked {updated} reports as under review.')
    mark_as_reviewing.short_description = "Mark as reviewing"

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'reporter', 'reviewed_by', 'influencer', 'trade_call'
        )


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    """
    Admin interface for user watchlists
    """
    list_display = [
        'id', 'user', 'influencer_display', 'added_at', 'has_notes'
    ]
    list_filter = ['added_at']
    search_fields = [
        'user__username', 'user__email',
        'influencer__channel_name', 'influencer__author_name',
        'notes'
    ]
    readonly_fields = ['added_at']
    fieldsets = [
        ('Watchlist Details', {
            'fields': ['user', 'influencer', 'notes', 'added_at']
        }),
    ]
    date_hierarchy = 'added_at'

    def influencer_display(self, obj):
        """Display influencer with platform"""
        return format_html(
            '{} <span style="color: #6c757d; font-size: 11px;">({})</span>',
            obj.influencer.channel_name,
            obj.influencer.platform
        )
    influencer_display.short_description = 'Influencer'

    def has_notes(self, obj):
        """Show if user has notes"""
        if obj.notes:
            return format_html(
                '<span style="color: #28a745;">✓ Yes</span>'
            )
        return format_html(
            '<span style="color: #6c757d;">✗ No</span>'
        )
    has_notes.short_description = 'Notes'

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'user', 'influencer'
        )

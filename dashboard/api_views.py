"""
API views for dashboard real-time data
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum
from datetime import timedelta
from math import ceil
import json
import requests
from decimal import Decimal

from .models import InfluencerSubmission, NotificationRead
from influencers.models import Influencer, TradeCall, Asset
from .services.notifications import build_user_notifications
from .services.search_service import perform_influencer_search
from .constants import (
    SUPPORTED_SEARCH_PLATFORMS,
    SUPPORTED_SEARCH_CATEGORIES,
    SUPPORTED_PLATFORM_VALUES,
    SUPPORTED_CATEGORY_VALUES,
)


@require_http_methods(["GET"])
@login_required
def dashboard_stats_api(request):
    """
    API endpoint for real-time dashboard statistics
    """
    try:
        # Date ranges
        now = timezone.now()
        today = now.date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        week_ago = now - timedelta(days=7)
        
        # Core statistics
        total_influencers = Influencer.objects.count()
        total_submissions = InfluencerSubmission.objects.count()
        pending_submissions = InfluencerSubmission.objects.filter(status='pending').count()
        
        # Approval metrics
        approved_submissions = InfluencerSubmission.objects.filter(status='approved').count()
        auto_approved_count = InfluencerSubmission.objects.filter(auto_approved=True).count()
        
        approval_rate = round((approved_submissions / total_submissions * 100)) if total_submissions > 0 else 0
        auto_approval_rate = round((auto_approved_count / total_submissions * 100)) if total_submissions > 0 else 0
        
        # Today's activity
        auto_approved_today = InfluencerSubmission.objects.filter(
            created_at__gte=today_start,
            auto_approved=True,
            status='approved'
        ).count()
        
        # Trade call metrics - only valid tracked calls (status='True')
        total_trade_calls = TradeCall.objects.filter(status='True').count()
        active_calls = TradeCall.objects.filter(status='True', done=False).count()
        successful_calls = TradeCall.objects.filter(status='True', target_hit=True).count()
        failed_calls = TradeCall.objects.filter(status='True', stoploss_hit=True).count()
        total_resolved_calls = successful_calls + failed_calls

        success_rate = round((successful_calls / total_resolved_calls * 100)) if total_resolved_calls > 0 else 0
        
        # Last processed
        last_submission = InfluencerSubmission.objects.filter(
            status__in=['approved', 'rejected']
        ).order_by('-updated_at').first()
        
        data = {
            'total_influencers': total_influencers,
            'total_submissions': total_submissions,
            'pending_submissions': pending_submissions,
            'approval_rate': approval_rate,
            'auto_approval_rate': auto_approval_rate,
            'auto_approved_today': auto_approved_today,
            'success_rate': success_rate,
            'total_trade_calls': total_trade_calls,
            'active_calls': active_calls,
            'last_processed': last_submission.updated_at.isoformat() if last_submission else None,
            'timestamp': now.isoformat()
        }
        
        return JsonResponse({'success': True, 'data': data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
@login_required
def submission_timeline_api(request):
    """
    API endpoint for submission timeline data
    """
    try:
        period = request.GET.get('period', '7')  # days
        period_days = int(period)
        
        now = timezone.now()
        start_date = now - timedelta(days=period_days)
        
        # Get daily submission counts
        daily_data = []
        for i in range(period_days):
            day = start_date + timedelta(days=i)
            day_start = timezone.make_aware(timezone.datetime.combine(day.date(), timezone.datetime.min.time()))
            day_end = timezone.make_aware(timezone.datetime.combine(day.date(), timezone.datetime.max.time()))
            
            submissions = InfluencerSubmission.objects.filter(
                created_at__range=[day_start, day_end]
            ).count()
            
            approvals = InfluencerSubmission.objects.filter(
                created_at__range=[day_start, day_end],
                status='approved'
            ).count()
            
            daily_data.append({
                'date': day.date().strftime('%m/%d'),
                'submissions': submissions,
                'approvals': approvals
            })
        
        return JsonResponse({'success': True, 'data': daily_data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
@login_required
def platform_distribution_api(request):
    """
    API endpoint for platform distribution data
    """
    try:
        # Get platform statistics
        platform_stats = InfluencerSubmission.objects.filter(
            status='approved'
        ).values('platform').annotate(
            count=Count('platform'),
            avg_score=Avg('approval_score'),
            avg_followers=Avg('follower_count')
        ).order_by('-count')
        
        # Format data for charts
        chart_data = []
        for stat in platform_stats:
            chart_data.append({
                'platform': stat['platform'],
                'count': stat['count'],
                'avg_score': round(stat['avg_score']) if stat['avg_score'] else 0,
                'avg_followers': int(stat['avg_followers']) if stat['avg_followers'] else 0
            })
        
        return JsonResponse({'success': True, 'data': chart_data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
@login_required
def recent_activity_api(request):
    """
    API endpoint for recent activity feed
    """
    try:
        limit = int(request.GET.get('limit', '10'))
        
        # Get recent submissions
        recent_submissions = InfluencerSubmission.objects.select_related(
            'submitted_by'
        ).order_by('-created_at')[:limit]
        
        activity_data = []
        for submission in recent_submissions:
            activity_data.append({
                'id': submission.id,
                'channel_name': submission.channel_name,
                'platform': submission.platform,
                'status': submission.status,
                'auto_approved': submission.auto_approved,
                'approval_score': submission.approval_score,
                'created_at': submission.created_at.isoformat(),
                'submitted_by': submission.submitted_by.username if submission.submitted_by else 'Unknown'
            })
        
        return JsonResponse({'success': True, 'data': activity_data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
@login_required
def user_notifications_api(request):
    """
    API endpoint for user notifications (watchlist + submissions)
    """
    try:
        limit = int(request.GET.get('limit', '15'))
    except (TypeError, ValueError):
        limit = 15

    try:
        notifications = build_user_notifications(request.user, limit=limit)
        unread_count = sum(1 for item in notifications if item.get('unread'))

        return JsonResponse({
            'notifications': notifications,
            'unread_count': unread_count
        })
    except Exception as exc:
        return JsonResponse({
            'notifications': [],
            'unread_count': 0,
            'error': str(exc)
        }, status=500)


@require_http_methods(["GET"])
@login_required
def top_performers_api(request):
    """
    API endpoint for top performing influencers
    """
    try:
        limit = int(request.GET.get('limit', '10'))
        
        # Get top performers by approval score
        top_performers = InfluencerSubmission.objects.filter(
            status='approved'
        ).select_related('submitted_by').order_by('-approval_score', '-follower_count')[:limit]
        
        performers_data = []
        for idx, submission in enumerate(top_performers, 1):
            performers_data.append({
                'rank': idx,
                'channel_name': submission.channel_name,
                'author_name': submission.author_name,
                'platform': submission.platform,
                'follower_count': submission.follower_count,
                'approval_score': submission.approval_score,
                'verified': submission.verified,
                'url': submission.url
            })
        
        return JsonResponse({'success': True, 'data': performers_data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
@login_required
def trade_calls_api(request):
    """
    API endpoint for recent trade calls
    """
    try:
        limit = int(request.GET.get('limit', '10'))
        
        # Get recent trade calls - only valid tracked calls (status='True')
        recent_calls = TradeCall.objects.filter(
            status='True'
        ).select_related(
            'influencer', 'asset'
        ).order_by('-created_at')[:limit]
        
        calls_data = []
        for call in recent_calls:
            asset = call.asset
            calls_data.append({
                'id': call.id,
                'uuid': call.uuid,
                'asset_symbol': asset.symbol if asset else None,
                'asset_name': asset.name if asset else None,
                'signal': call.signal,
                'entry_price': call.entry_price,
                'assumed_entry_price': float(call.assumed_entry_price) if call.assumed_entry_price else None,
                'status': call.status,
                'created_at': call.created_at.isoformat() if call.created_at else None,
                'influencer_name': call.influencer.channel_name if call.influencer else 'Unknown',
                'target_hit': call.target_hit,
                'stoploss_hit': call.stoploss_hit
            })
        
        return JsonResponse({'success': True, 'data': calls_data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})




@require_http_methods(["POST"])
@login_required
def refresh_dashboard_data(request):
    """
    API endpoint to trigger dashboard data refresh
    """
    try:
        # You could trigger background tasks here
        # For now, just return success

        return JsonResponse({
            'success': True,
            'message': 'Dashboard data refresh triggered',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
def search_influencers_api(request):
    """
    API endpoint for searching influencers
    """
    try:
        def parse_int(value, default):
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                return default

        payload = perform_influencer_search(
            query=request.GET.get('q', ''),
            platform=request.GET.get('platform', ''),
            category=request.GET.get('category', ''),
            sort_by=request.GET.get('sort', 'relevance'),
            page=parse_int(request.GET.get('page'), 1),
            page_size=parse_int(request.GET.get('page_size'), 12),
        )

        return JsonResponse(payload)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def mark_notification_read_api(request):
    """
    API endpoint to mark a notification as read for the current user
    """
    try:
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        if not notification_id:
            return JsonResponse({'success': False, 'error': 'notification_id is required'}, status=400)
        
        # Determine notification type from ID prefix
        notification_type = 'call' if notification_id.startswith('call-') else 'submission'
        
        # Create or get the read record
        read_record, created = NotificationRead.objects.get_or_create(
            user=request.user,
            notification_id=notification_id,
            defaults={'notification_type': notification_type}
        )
        
        return JsonResponse({
            'success': True,
            'notification_id': notification_id,
            'was_new': created
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def mark_all_notifications_read_api(request):
    """
    API endpoint to mark all notifications as read for the current user
    """
    try:
        # Get current notifications to mark them as read
        notifications = build_user_notifications(request.user, limit=100)  # Get more to mark all as read
        
        read_records = []
        for notification in notifications:
            if notification.get('unread'):
                notification_type = 'call' if notification['id'].startswith('call-') else 'submission'
                read_records.append(
                    NotificationRead(
                        user=request.user,
                        notification_id=notification['id'],
                        notification_type=notification_type
                    )
                )
        
        # Bulk create read records, ignoring duplicates
        if read_records:
            NotificationRead.objects.bulk_create(read_records, ignore_conflicts=True)
        
        return JsonResponse({
            'success': True,
            'marked_count': len(read_records)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
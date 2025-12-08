from datetime import timedelta
from typing import List, Dict

from django.utils import timezone

from dashboard.models import InfluencerSubmission, Watchlist, NotificationRead
from influencers.models import TradeCall


def _format_time_ago(timestamp, now):
    if not timestamp:
        return 'Just now'

    if timezone.is_naive(timestamp):
        timestamp = timezone.make_aware(timestamp)

    diff = now - timestamp
    seconds = diff.total_seconds()

    if seconds < 60:
        return 'Just now'
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}m ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}h ago"
    days = int(seconds // 86400)
    return f"{days}d ago"


def build_user_notifications(user, limit=15) -> List[Dict]:
    """
    Build a combined list of signal + submission notifications for the user.
    Returned items contain:
        id, type, icon, title, message, time, timestamp, unread, category
    """
    now = timezone.now()
    unread_threshold = now - timedelta(hours=24)
    notifications = []
    
    # Get user's read notification IDs for efficient lookup
    read_notification_ids = set(
        NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    )

    watchlist_influencer_ids = list(
        Watchlist.objects.filter(user=user).values_list('influencer__influencer_id', flat=True)
    )

    if watchlist_influencer_ids:
        trade_calls = TradeCall.objects.filter(
            status='True',
            influencer__influencer_id__in=watchlist_influencer_ids
        ).select_related('influencer', 'asset').order_by('-timestamp')[:limit]

        for call in trade_calls:
            ts = call.timestamp or now
            influencer_name = call.influencer.channel_name if call.influencer else 'Unknown influencer'
            asset_symbol = call.asset.symbol if call.asset else 'Asset'
            status = 'target hit' if call.target_hit else 'stopped' if call.stoploss_hit else 'active'

            notif_type = 'success' if call.target_hit else 'danger' if call.stoploss_hit else 'info'
            title = f"{influencer_name} {('hit target' if call.target_hit else 'shared a call')}"
            message = f"{asset_symbol} signal is {status}."
            
            notification_id = f"call-{call.id}"
            is_unread = (ts >= unread_threshold) and (notification_id not in read_notification_ids)

            notifications.append({
                'id': notification_id,
                'type': notif_type,
                'icon': 'fa-chart-line',
                'title': title,
                'message': message,
                'timestamp': ts,
                'time': _format_time_ago(ts, now),
                'unread': is_unread,
                'category': 'signals'
            })

    # Submission updates for the current user
    submissions = InfluencerSubmission.objects.filter(
        submitted_by=user
    ).order_by('-updated_at')[:limit]

    for submission in submissions:
        ts = submission.updated_at or submission.created_at or now
        status = submission.status
        if status == 'approved':
            notif_type = 'success'
            icon = 'fa-check-circle'
            title = f"{submission.channel_name} approved"
            message = "Your submission has been approved."
        elif status == 'rejected':
            notif_type = 'danger'
            icon = 'fa-times-circle'
            title = f"{submission.channel_name} rejected"
            message = submission.rejection_reason or "Your submission was rejected."
        else:
            notif_type = 'warning'
            icon = 'fa-hourglass-half'
            title = f"{submission.channel_name} pending review"
            message = "We're still reviewing this submission."

        notification_id = f"submission-{submission.id}"
        is_unread = (ts >= unread_threshold and status in ('approved', 'rejected')) and (notification_id not in read_notification_ids)

        notifications.append({
            'id': notification_id,
            'type': notif_type,
            'icon': icon,
            'title': title,
            'message': message,
            'timestamp': ts,
            'time': _format_time_ago(ts, now),
            'unread': is_unread,
            'category': 'submissions'
        })

    notifications.sort(key=lambda item: item['timestamp'], reverse=True)
    trimmed = notifications[:limit]

    # Convert timestamps to ISO strings for JSON responses
    for notif in trimmed:
        ts = notif['timestamp']
        notif['timestamp'] = ts.isoformat() if ts else None

    return trimmed

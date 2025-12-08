def pending_submissions_count(request):
    """
    Context processor to add pending submissions count to all templates
    """
    if request.user.is_authenticated:
        try:
            from .models import InfluencerSubmission
            count = InfluencerSubmission.objects.filter(status='pending').count()
            return {'pending_submissions_count': count}
        except ImportError:
            return {'pending_submissions_count': 0}
    return {'pending_submissions_count': 0}


def unread_notifications_count(request):
    """
    Context processor to add unread notifications count to all templates
    """
    if request.user.is_authenticated:
        try:
            from .services.notifications import build_user_notifications
            notifications = build_user_notifications(request.user, limit=10)
            count = sum(1 for item in notifications if item.get('unread'))
            return {'unread_notifications_count': count}
        except Exception:
            return {'unread_notifications_count': 0}
    return {'unread_notifications_count': 0}

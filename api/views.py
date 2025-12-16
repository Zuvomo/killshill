from django.shortcuts import render
from django.db.models import Q, Count, Avg
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from influencers.models import Influencer, Asset, TradeCall
from .serializers import InfluencerSerializer, AssetSerializer, TradeCallSerializer, InfluencerSubmissionSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([AllowAny])
def leaderboard_api(request):
    """
    API endpoint for KOL Leaderboard data
    """
    category = request.GET.get('category', 'all')  # all, crypto, stocks, forex
    platform = request.GET.get('platform', 'all')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    # Base queryset
    queryset = Influencer.objects.all()
    
    # Apply filters based on category (using asset types from trade calls)
    if category != 'all':
        category_map = {
            'crypto': 'crypto',
            'stocks': 'stocks', 
            'forex': 'forex'
        }
        if category in category_map:
            queryset = queryset.filter(
                tradecall__asset__asset_type__icontains=category_map[category]
            ).distinct()
    
    # Filter by platform
    if platform != 'all':
        queryset = queryset.filter(platform__icontains=platform)
    
    # Calculate performance metrics
    influencers_data = []
    for influencer in queryset:
        # Get trade calls for this influencer - ONLY valid tracked calls (status='True')
        trade_calls = TradeCall.objects.filter(
            influencer=influencer,
            status='True'  # Only calls with sufficient signal details
        )

        # Calculate accuracy based on resolved calls
        total_calls = trade_calls.count()
        successful_calls = trade_calls.filter(target_hit=True).count() if total_calls > 0 else 0
        failed_calls = trade_calls.filter(stoploss_hit=True).count() if total_calls > 0 else 0
        resolved_calls = successful_calls + failed_calls
        accuracy = (successful_calls / resolved_calls * 100) if resolved_calls > 0 else 0
        
        # Get primary category based on most trade calls
        primary_category = 'crypto'  # Default
        if trade_calls.exists():
            category_counts = trade_calls.values('asset__asset_type').annotate(
                count=Count('id')
            ).order_by('-count')
            if category_counts:
                primary_category = category_counts[0]['asset__asset_type'] or 'crypto'

        # Calculate real risk-reward ratio (median RR from successful calls)
        rr_values = []
        for call in trade_calls.filter(target_hit=True, assumed_entry_price__gt=0, stoploss_price__gt=0):
            try:
                # RR = (target - entry) / (entry - stoploss)
                target_price = call.target_first or 0
                if target_price > 0:
                    reward = abs(target_price - call.assumed_entry_price)
                    risk = abs(call.assumed_entry_price - call.stoploss_price)
                    if risk > 0:
                        rr = reward / risk
                        rr_values.append(rr)
            except:
                continue

        # Calculate median RR
        if rr_values:
            rr_values.sort()
            median_idx = len(rr_values) // 2
            median_rr = round(rr_values[median_idx], 1)
        else:
            median_rr = 0.0

        # Calculate median time to target (in days) from calls that hit target
        tt_values = []
        for call in trade_calls.filter(target_hit=True, target_achieved_at__isnull=False):
            try:
                time_diff = call.target_achieved_at - call.timestamp
                days = time_diff.total_seconds() / 86400  # Convert to days
                tt_values.append(days)
            except:
                continue

        # Calculate median TT
        if tt_values:
            tt_values.sort()
            median_idx = len(tt_values) // 2
            median_tt = round(tt_values[median_idx], 1)
        else:
            median_tt = 0.0

        # Calculate confidence score based on multiple factors
        # Factors: accuracy (40%), total calls (20%), resolved calls ratio (20%), RR (10%), consistency (10%)
        confidence = 0

        # Accuracy component (0-40 points)
        confidence += min(accuracy * 0.4, 40)

        # Total calls component (0-20 points) - more calls = more confidence
        if total_calls >= 100:
            confidence += 20
        elif total_calls >= 50:
            confidence += 15
        elif total_calls >= 20:
            confidence += 10
        elif total_calls >= 10:
            confidence += 5

        # Resolved calls ratio (0-20 points) - higher % of resolved calls = more confidence
        if total_calls > 0:
            resolved_ratio = resolved_calls / total_calls
            confidence += resolved_ratio * 20

        # Risk-Reward component (0-10 points)
        if median_rr >= 3:
            confidence += 10
        elif median_rr >= 2:
            confidence += 7
        elif median_rr >= 1:
            confidence += 5
        elif median_rr > 0:
            confidence += 2

        # Recent activity component (0-10 points) - active in last 7 days?
        from django.utils import timezone
        from datetime import timedelta
        last_week = timezone.now() - timedelta(days=7)
        recent_calls_count = trade_calls.filter(timestamp__gte=last_week).count()
        if recent_calls_count >= 5:
            confidence += 10
        elif recent_calls_count >= 3:
            confidence += 7
        elif recent_calls_count >= 1:
            confidence += 5

        confidence = min(int(confidence), 100)
        
        influencers_data.append({
            'id': influencer.influencer_id,
            'username': influencer.channel_name or f"user_{influencer.influencer_id}",
            'display_name': influencer.author_name or influencer.channel_name,
            'platform': influencer.platform or 'twitter',
            'accuracy': round(accuracy, 1),
            'category': primary_category,
            'total_calls': total_calls,
            'median_risk_reward': median_rr,
            'median_time_to_target': f"{median_tt}d",
            'confidence_score': confidence,
            'platforms': [influencer.platform] if influencer.platform else ['twitter'],
        })
    
    # Sort by accuracy descending
    influencers_data.sort(key=lambda x: x['accuracy'], reverse=True)
    
    # Pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_data = influencers_data[start_idx:end_idx]
    
    return Response({
        'results': paginated_data,
        'count': len(influencers_data),
        'page': page,
        'page_size': page_size,
        'total_pages': (len(influencers_data) + page_size - 1) // page_size
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def trending_kols_api(request):
    """
    API endpoint for Trending KOLs by category - Based on recent activity (last 7 days)
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Case, When, FloatField

    # Get date range for trending (last 7 days)
    last_week = timezone.now() - timedelta(days=7)
    two_weeks_ago = timezone.now() - timedelta(days=14)

    def get_trending_for_category(asset_type):
        """Get trending influencers for a specific asset type"""
        # Get influencers with calls in the last 7 days for this category
        recent_influencers = TradeCall.objects.filter(
            timestamp__gte=last_week,
            status='True',
            asset__asset_type=asset_type
        ).values('influencer').annotate(
            recent_calls=Count('id'),
            recent_accuracy=Avg(
                Case(
                    When(target_hit=True, then=100.0),
                    When(stoploss_hit=True, then=0.0),
                    default=None,
                    output_field=FloatField()
                )
            )
        ).filter(recent_calls__gte=1).order_by('-recent_calls', '-recent_accuracy')[:10]

        trending_list = []
        for rank, inf_data in enumerate(recent_influencers, start=1):
            try:
                influencer = Influencer.objects.get(influencer_id=inf_data['influencer'])

                # Get previous week's call count to determine trend
                prev_week_calls = TradeCall.objects.filter(
                    influencer=influencer,
                    timestamp__gte=two_weeks_ago,
                    timestamp__lt=last_week,
                    status='True',
                    asset__asset_type=asset_type
                ).count()

                # Determine trend (up if more calls this week than last week)
                trend = 'up' if inf_data['recent_calls'] > prev_week_calls else 'down' if inf_data['recent_calls'] < prev_week_calls else 'stable'

                # Get total calls (all time)
                total_calls = TradeCall.objects.filter(
                    influencer=influencer,
                    status='True'
                ).count()

                trending_list.append({
                    'rank': rank,
                    'username': influencer.channel_name or f"user_{influencer.influencer_id}",
                    'handle': f"@{influencer.channel_name.lower().replace(' ', '')}" if influencer.channel_name else f"@user{influencer.influencer_id}",
                    'accuracy': round(inf_data['recent_accuracy'] or 0, 1),
                    'total_calls': total_calls,
                    'recent_calls': inf_data['recent_calls'],
                    'trend': trend
                })
            except Influencer.DoesNotExist:
                continue

        return trending_list

    # Build trending data for each category
    trending_data = {
        'crypto': get_trending_for_category('crypto'),
        'stocks': get_trending_for_category('stocks'),
        'forex': get_trending_for_category('forex')
    }

    return Response(trending_data)


@api_view(['GET'])
@permission_classes([AllowAny])
def top_signals_api(request):
    """
    API endpoint for Top Signals data
    """
    from django.utils import timezone
    from datetime import timedelta

    # Get recent trade calls with valid results (target_hit is not null)
    recent_calls = TradeCall.objects.select_related('influencer', 'asset').filter(
        target_hit__isnull=False  # Only include calls that have been resolved
    ).order_by('-created_at')[:10]

    def get_time_ago(timestamp):
        """Calculate human-readable time ago"""
        if not timestamp:
            return 'Unknown'

        now = timezone.now()
        diff = now - timestamp

        if diff.days > 365:
            years = diff.days // 365
            return f"{years}y ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months}mo ago"
        elif diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"

    signals_data = []
    for call in recent_calls:
        signals_data.append({
            'id': call.id,
            'influencer': {
                'username': call.influencer.channel_name if call.influencer else 'Unknown',
                'handle': f"@{call.influencer.channel_name.lower()}" if call.influencer and call.influencer.channel_name else '@unknown',
                'platform': call.influencer.platform if call.influencer else 'twitter'
            },
            'asset': {
                'symbol': call.asset.symbol,
                'name': call.asset.name
            },
            'signal_type': call.signal or 'buy',
            'entry_price': call.assumed_entry_price or 0,
            'target_price': call.target_first or 0,
            'status': call.status or 'pending',
            'accuracy_status': 'accurate' if call.target_hit else 'inaccurate',
            'time_ago': get_time_ago(call.timestamp),
            'description': call.description or call.text or 'Trading signal'
        })

    return Response(signals_data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_influencer_api(request):
    """
    API endpoint for influencer submission with auto-approval logic
    """
    serializer = InfluencerSubmissionSerializer(data=request.data)
    
    if serializer.is_valid():
        # Auto-approval logic
        platform_url = serializer.validated_data.get('platform_url', '')
        follower_count = serializer.validated_data.get('follower_count', 0)
        
        # Simple auto-approval criteria
        auto_approve = False
        if follower_count >= 1000:  # Auto-approve if >1k followers
            auto_approve = True
        elif 'twitter.com' in platform_url or 'telegram.me' in platform_url:
            auto_approve = True
        
        # Create influencer entry (to be added to existing table via Django ORM)
        influencer_data = {
            'channel_name': serializer.validated_data.get('username'),
            'url': serializer.validated_data.get('platform_url'),
            'platform': serializer.validated_data.get('platform'),
            'author_name': serializer.validated_data.get('display_name', serializer.validated_data.get('username')),
        }
        
        return Response({
            'message': 'Influencer submitted successfully',
            'auto_approved': auto_approve,
            'status': 'approved' if auto_approve else 'pending_review',
            'data': influencer_data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def search_influencers_api(request):
    """
    API endpoint for searching influencers with complete statistics.
    When no query is supplied, returns top performers by total tracked calls.
    """
    query = (request.GET.get('q') or '').strip()
    platform = request.GET.get('platform', 'all')
    category = request.GET.get('category', 'all')
    sort_by = request.GET.get('sort', 'relevance')
    try:
        limit = min(max(int(request.GET.get('limit', 20)), 1), 50)
    except (TypeError, ValueError):
        limit = 20

    queryset = Influencer.objects.all()

    if query:
        queryset = queryset.filter(
            Q(channel_name__icontains=query) |
            Q(author_name__icontains=query) |
            Q(url__icontains=query)
        )

    if platform and platform != 'all':
        queryset = queryset.filter(platform__icontains=platform)

    if category and category != 'all':
        queryset = queryset.filter(
            tradecall__asset__asset_type__icontains=category
        ).distinct()

    # Annotate base statistics
    queryset = queryset.annotate(
        total_calls=Count('tradecall', filter=Q(tradecall__status='True')),
        successful_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__target_hit=True)),
        failed_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__stoploss_hit=True)),
    )

    if not query:
        queryset = queryset.filter(total_calls__gt=0)
        queryset = queryset.order_by('-total_calls', '-successful_calls')
    else:
        queryset = queryset.order_by('-total_calls')

    results = []
    influencer_list = list(queryset[:limit])

    # Preload recent trade calls to determine category if needed
    influencer_ids = [inf.influencer_id for inf in influencer_list]
    trade_calls_map = {inf_id: [] for inf_id in influencer_ids}
    trade_calls = TradeCall.objects.filter(
        status='True',
        influencer_id__in=influencer_ids
    ).select_related('asset')

    for call in trade_calls:
        trade_calls_map.setdefault(call.influencer_id, []).append(call)

    for influencer in influencer_list:
        resolved_calls = (influencer.successful_calls or 0) + (influencer.failed_calls or 0)
        accuracy = round((influencer.successful_calls / resolved_calls) * 100, 1) if resolved_calls > 0 else 0

        primary_category = 'crypto'
        calls_for_inf = trade_calls_map.get(influencer.influencer_id, [])
        if calls_for_inf:
            category_counts = {}
            for call in calls_for_inf[:25]:
                asset_type = (call.asset.asset_type or '').lower() if call.asset else ''
                if 'stock' in asset_type:
                    key = 'stocks'
                elif 'forex' in asset_type or 'fx' in asset_type:
                    key = 'forex'
                elif 'commodit' in asset_type or 'gold' in asset_type or 'oil' in asset_type:
                    key = 'commodities'
                else:
                    key = 'crypto'
                category_counts[key] = category_counts.get(key, 0) + 1
            if category_counts:
                primary_category = max(category_counts, key=category_counts.get)

        results.append({
            'id': influencer.influencer_id,
            'channel_name': influencer.channel_name or f"user_{influencer.influencer_id}",
            'author_name': influencer.author_name or influencer.channel_name or '',
            'username': influencer.channel_name or '',
            'display_name': influencer.author_name or '',
            'platform': influencer.platform or 'Unknown',
            'url': influencer.url,
            'total_calls': influencer.total_calls or 0,
            'successful_calls': influencer.successful_calls or 0,
            'failed_calls': influencer.failed_calls or 0,
            'accuracy': accuracy,
            'category': primary_category,
        })

    if sort_by == 'accuracy':
        results.sort(key=lambda x: x['accuracy'], reverse=True)
    elif sort_by == 'calls':
        results.sort(key=lambda x: x['total_calls'], reverse=True)
    elif sort_by == 'name':
        results.sort(key=lambda x: x['channel_name'] or '')

    return Response({'results': results})


@api_view(['GET'])
@permission_classes([AllowAny])
def analytics_data_api(request):
    """
    API endpoint for analytics dashboard data - Real-time calculations
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Case, When, Avg, F, ExpressionWrapper, DurationField

    # Get recent calls (last 30 days for analytics)
    last_30_days = timezone.now() - timedelta(days=30)

    # Calculate consensus index (% of BUY vs SELL signals by category)
    def get_consensus(asset_type):
        calls = TradeCall.objects.filter(
            timestamp__gte=last_30_days,
            status='True',
            asset__asset_type=asset_type
        )
        total = calls.count()
        if total == 0:
            return 50  # Neutral

        buy_count = calls.filter(signal__iexact='buy').count()
        bullish_percentage = round((buy_count / total) * 100)
        return bullish_percentage

    crypto_bullish = get_consensus('crypto')
    stocks_bullish = get_consensus('stocks')
    forex_bullish = get_consensus('forex')

    # Overall sentiment
    avg_bullish = (crypto_bullish + stocks_bullish + forex_bullish) / 3
    overall_sentiment = 'bullish' if avg_bullish > 55 else 'bearish' if avg_bullish < 45 else 'neutral'

    # Speed leaders - influencers with fastest time to target
    # Calculate average time from entry to target hit
    speed_leaders_query = TradeCall.objects.filter(
        timestamp__gte=last_30_days,
        status='True',
        target_hit=True,
        target_achieved_at__isnull=False
    ).values('influencer').annotate(
        call_count=Count('id'),
        avg_time_hours=Avg(
            ExpressionWrapper(
                F('target_achieved_at') - F('timestamp'),
                output_field=DurationField()
            )
        )
    ).filter(call_count__gte=3).order_by('avg_time_hours')[:3]

    speed_leaders = []
    for rank, leader in enumerate(speed_leaders_query, start=1):
        try:
            influencer = Influencer.objects.get(influencer_id=leader['influencer'])
            avg_hours = leader['avg_time_hours'].total_seconds() / 3600 if leader['avg_time_hours'] else 0
            speed_leaders.append({
                'rank': rank,
                'username': influencer.channel_name or f"user_{influencer.influencer_id}",
                'avg_time': f"{avg_hours:.1f}h"
            })
        except Influencer.DoesNotExist:
            continue

    # Asset heatmap - most traded assets per category (hot if many calls)
    def get_asset_heatmap(asset_type):
        assets = TradeCall.objects.filter(
            timestamp__gte=last_30_days,
            status='True',
            asset__asset_type=asset_type
        ).values('asset__symbol').annotate(
            call_count=Count('id')
        ).order_by('-call_count')[:10]

        # Determine heat level based on call count
        heatmap = {}
        if assets:
            max_calls = assets[0]['call_count'] if assets else 1
            for asset in assets:
                symbol = asset['asset__symbol'].lower()
                calls = asset['call_count']
                # Hot: >70% of max, Warm: 40-70%, Cold: <40%
                if calls / max_calls > 0.7:
                    heatmap[symbol] = 'hot'
                elif calls / max_calls > 0.4:
                    heatmap[symbol] = 'warm'
                else:
                    heatmap[symbol] = 'cold'

        return heatmap

    # Risk analysis - categorize calls by risk level (based on stop-loss distance)
    risk_calls = TradeCall.objects.filter(
        timestamp__gte=last_30_days,
        status='True',
        assumed_entry_price__gt=0,
        stoploss_price__gt=0
    )

    total_risk_calls = risk_calls.count()
    if total_risk_calls > 0:
        # Risk = (entry - stoploss) / entry * 100
        # Low risk: <5%, Medium: 5-15%, High: >15%
        low_risk = 0
        medium_risk = 0
        high_risk = 0

        for call in risk_calls:
            try:
                risk_pct = abs(call.assumed_entry_price - call.stoploss_price) / call.assumed_entry_price * 100
                if risk_pct < 5:
                    low_risk += 1
                elif risk_pct < 15:
                    medium_risk += 1
                else:
                    high_risk += 1
            except:
                continue

        low_risk_pct = round((low_risk / total_risk_calls) * 100)
        medium_risk_pct = round((medium_risk / total_risk_calls) * 100)
        high_risk_pct = round((high_risk / total_risk_calls) * 100)
    else:
        # Default values if no data
        low_risk_pct, medium_risk_pct, high_risk_pct = 35, 45, 20

    analytics_data = {
        'consensus_index': {
            'crypto_bullish': crypto_bullish,
            'stocks_bullish': stocks_bullish,
            'forex_bullish': forex_bullish,
            'overall_sentiment': overall_sentiment
        },
        'speed_leaders': speed_leaders,
        'asset_heatmap': {
            'crypto': get_asset_heatmap('crypto'),
            'stocks': get_asset_heatmap('stocks'),
            'forex': get_asset_heatmap('forex')
        },
        'risk_analysis': {
            'low_risk': low_risk_pct,
            'medium_risk': medium_risk_pct,
            'high_risk': high_risk_pct
        }
    }

    return Response(analytics_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats_api(request):
    """
    API endpoint for dashboard statistics
    """
    from django.utils import timezone
    from datetime import timedelta
    from dashboard.models import InfluencerSubmission
    
    # Calculate today's stats
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Basic counts
    total_influencers = Influencer.objects.count()
    total_submissions = InfluencerSubmission.objects.count()
    
    # Auto-approved today
    auto_approved_today = InfluencerSubmission.objects.filter(
        created_at__gte=today_start,
        auto_approved=True,
        status='approved'
    ).count()
    
    # Pending submissions
    pending_review = InfluencerSubmission.objects.filter(status='pending').count()
    
    # Calculate approval rate
    approved_submissions = InfluencerSubmission.objects.filter(status='approved').count()
    approval_rate = round((approved_submissions / total_submissions * 100)) if total_submissions > 0 else 85
    
    # Last processed time
    last_submission = InfluencerSubmission.objects.filter(status='approved').order_by('-updated_at').first()
    last_processed = last_submission.updated_at.isoformat() if last_submission else None
    
    # Manual review today count
    manual_review_today = InfluencerSubmission.objects.filter(
        created_at__gte=today_start,
        auto_approved=False,
        status='approved'
    ).count()
    
    stats_data = {
        'active_influencers': total_influencers,
        'auto_approved_today': auto_approved_today,
        'pending_review': pending_review,
        'approval_rate': approval_rate,
        'last_processed': last_processed,
        'manual_review_today': manual_review_today,
        'total_submissions': total_submissions
    }
    
    return Response(stats_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_submissions_api(request):
    """
    API endpoint for recent submissions data
    """
    from dashboard.models import InfluencerSubmission
    
    # Get recent submissions (last 10)
    submissions = InfluencerSubmission.objects.select_related('submitted_by').order_by('-created_at')[:10]
    
    submissions_data = []
    for submission in submissions:
        submissions_data.append({
            'id': submission.id,
            'channel_name': submission.channel_name,
            'author_name': submission.author_name,
            'platform': submission.platform,
            'status': submission.status,
            'auto_approved': submission.auto_approved,
            'approval_score': submission.approval_score,
            'created_at': submission.created_at.isoformat(),
            'submitted_by': submission.submitted_by.username if submission.submitted_by else 'Unknown'
        })
    
    return Response({
        'results': submissions_data,
        'count': len(submissions_data)
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_submission_api(request, submission_id):
    """
    API endpoint to manually process a specific submission
    """
    from dashboard.models import InfluencerSubmission
    from django.utils import timezone
    
    try:
        submission = InfluencerSubmission.objects.get(id=submission_id, status='pending')
        
        # Mock processing logic - in reality this would call the auto-approval service
        # For now, we'll approve it
        submission.status = 'approved'
        submission.auto_approved = False
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.approval_score = 75  # Mock score
        submission.save()
        
        return Response({
            'success': True,
            'message': 'Submission processed successfully',
            'status': submission.status
        })
        
    except InfluencerSubmission.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Submission not found or already processed'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error processing submission: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_auto_approvals_api(request):
    """
    API endpoint to process all pending auto-approvals
    """
    from dashboard.models import InfluencerSubmission
    from django.utils import timezone

    try:
        # Get pending submissions
        pending_submissions = InfluencerSubmission.objects.filter(status='pending')
        processed_count = 0

        for submission in pending_submissions:
            # Mock auto-approval logic - in reality this would call the service
            if submission.approval_score >= 70:
                submission.status = 'approved'
                submission.auto_approved = True
                submission.reviewed_at = timezone.now()
                submission.save()
                processed_count += 1

        return Response({
            'success': True,
            'processed': processed_count,
            'message': f'Processed {processed_count} submissions'
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error processing auto-approvals: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def influencer_mini_profile_api(request, influencer_id):
    """
    API endpoint for influencer mini-profile (for tooltips/hover cards)
    Returns compact profile information
    """
    from django.utils import timezone
    from datetime import timedelta

    try:
        influencer = Influencer.objects.get(influencer_id=influencer_id)

        # Get all trade calls for this influencer
        trade_calls = TradeCall.objects.filter(
            influencer=influencer,
            status='True'
        )

        # Calculate statistics
        total_calls = trade_calls.count()
        successful_calls = trade_calls.filter(target_hit=True).count()
        failed_calls = trade_calls.filter(stoploss_hit=True).count()
        resolved_calls = successful_calls + failed_calls
        accuracy = round((successful_calls / resolved_calls * 100), 1) if resolved_calls > 0 else 0

        # Get asset focus (top 3 most traded assets)
        asset_focus = list(
            trade_calls.values('asset__symbol')
            .annotate(count=Count('id'))
            .order_by('-count')[:3]
            .values_list('asset__symbol', flat=True)
        )

        # Calculate average return percentage from successful calls
        avg_return = 0
        return_values = []
        for call in trade_calls.filter(target_hit=True, assumed_entry_price__gt=0):
            try:
                target_price = call.target_first or 0
                if target_price > 0 and call.assumed_entry_price > 0:
                    return_pct = ((target_price - call.assumed_entry_price) / call.assumed_entry_price) * 100
                    return_values.append(return_pct)
            except:
                continue

        if return_values:
            avg_return = round(sum(return_values) / len(return_values), 1)

        # Recent performance (last 7 days) - W-L format
        last_week = timezone.now() - timedelta(days=7)
        recent_calls = trade_calls.filter(timestamp__gte=last_week, target_hit__isnull=False)
        recent_wins = recent_calls.filter(target_hit=True).count()
        recent_losses = recent_calls.filter(stoploss_hit=True).count()
        recent_performance = f"{recent_wins}W-{recent_losses}L"

        # Get primary platform
        platform = influencer.platform or 'twitter'

        # Bio/Description (if available)
        bio = "Professional trader and market analyst"  # Default, can be enhanced

        profile_data = {
            'id': influencer.influencer_id,
            'channel_name': influencer.channel_name or f"user_{influencer.influencer_id}",
            'author_name': influencer.author_name or influencer.channel_name,
            'platform': platform,
            'url': influencer.url,
            'total_calls': total_calls,
            'accuracy': accuracy,
            'asset_focus': asset_focus,
            'avg_return': avg_return,
            'recent_performance': recent_performance,
            'bio': bio,
            'followers': 0,  # Can be enhanced with actual follower data if available
        }

        return Response(profile_data)

    except Influencer.DoesNotExist:
        return Response({
            'error': 'Influencer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error fetching profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_abuse_api(request):
    """
    API endpoint to submit abuse reports for trade calls or influencer profiles
    """
    from dashboard.models import AbuseReport

    report_type = request.data.get('report_type')  # 'call' or 'profile'
    reason = request.data.get('reason')
    description = request.data.get('description', '')
    influencer_id = request.data.get('influencer_id')
    trade_call_id = request.data.get('trade_call_id')

    # Validation
    if report_type not in ['call', 'profile']:
        return Response({
            'error': 'Invalid report type. Must be "call" or "profile".'
        }, status=status.HTTP_400_BAD_REQUEST)

    if not reason:
        return Response({
            'error': 'Reason is required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if report_type == 'call' and not trade_call_id:
        return Response({
            'error': 'trade_call_id is required for call reports.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if report_type == 'profile' and not influencer_id:
        return Response({
            'error': 'influencer_id is required for profile reports.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get IP address
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()

        # Create report
        report_data = {
            'reporter': request.user,
            'report_type': report_type,
            'reason': reason,
            'description': description,
            'ip_address': ip_address
        }

        if report_type == 'call':
            # Verify trade call exists
            try:
                trade_call = TradeCall.objects.get(id=trade_call_id)
                report_data['trade_call_id'] = trade_call.id
            except TradeCall.DoesNotExist:
                return Response({
                    'error': 'Trade call not found.'
                }, status=status.HTTP_404_NOT_FOUND)

        if report_type == 'profile':
            # Verify influencer exists
            try:
                influencer = Influencer.objects.get(influencer_id=influencer_id)
                report_data['influencer_id'] = influencer.influencer_id
            except Influencer.DoesNotExist:
                return Response({
                    'error': 'Influencer not found.'
                }, status=status.HTTP_404_NOT_FOUND)

        report = AbuseReport.objects.create(**report_data)

        return Response({
            'success': True,
            'message': 'Report submitted successfully. Our team will review it shortly.',
            'report_id': report.id
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Error submitting report: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def watchlist_api(request):
    """
    API endpoint for user watchlist
    GET: List all watched influencers
    POST: Add influencer to watchlist
    """
    from dashboard.models import Watchlist

    if request.method == 'GET':
        # Get user's watchlist
        watchlist = Watchlist.objects.filter(user=request.user).select_related('influencer')

        watchlist_data = []
        for item in watchlist:
            # Get quick stats for each influencer
            trade_calls = TradeCall.objects.filter(
                influencer_id=item.influencer.influencer_id,
                status='True'
            )
            total_calls = trade_calls.count()
            successful_calls = trade_calls.filter(target_hit=True).count()
            resolved_calls = successful_calls + trade_calls.filter(stoploss_hit=True).count()
            accuracy = round((successful_calls / resolved_calls * 100), 1) if resolved_calls > 0 else 0

            watchlist_data.append({
                'id': item.id,
                'influencer': {
                    'id': item.influencer.influencer_id,
                    'channel_name': item.influencer.channel_name,
                    'author_name': item.influencer.author_name,
                    'platform': item.influencer.platform,
                    'url': item.influencer.url
                },
                'stats': {
                    'total_calls': total_calls,
                    'accuracy': accuracy
                },
                'notes': item.notes,
                'added_at': item.added_at.isoformat()
            })

        return Response({
            'watchlist': watchlist_data,
            'count': len(watchlist_data)
        })

    elif request.method == 'POST':
        # Add to watchlist
        influencer_id = request.data.get('influencer_id')
        notes = request.data.get('notes', '')

        if not influencer_id:
            return Response({
                'error': 'influencer_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Verify influencer exists
            influencer = Influencer.objects.get(influencer_id=influencer_id)

            # Check if already in watchlist
            existing = Watchlist.objects.filter(
                user=request.user,
                influencer_id=influencer.influencer_id
            ).first()

            if existing:
                return Response({
                    'error': 'Influencer already in watchlist.',
                    'watchlist_id': existing.id
                }, status=status.HTTP_400_BAD_REQUEST)

            # Add to watchlist
            watchlist_item = Watchlist.objects.create(
                user=request.user,
                influencer_id=influencer.influencer_id,
                notes=notes
            )

            return Response({
                'success': True,
                'message': 'Influencer added to watchlist.',
                'watchlist_id': watchlist_item.id
            }, status=status.HTTP_201_CREATED)

        except Influencer.DoesNotExist:
            return Response({
                'error': 'Influencer not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': f'Error adding to watchlist: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def watchlist_remove_api(request, watchlist_id):
    """
    API endpoint to remove influencer from watchlist
    """
    from dashboard.models import Watchlist

    try:
        watchlist_item = Watchlist.objects.get(
            id=watchlist_id,
            user=request.user
        )
        watchlist_item.delete()

        return Response({
            'success': True,
            'message': 'Influencer removed from watchlist.'
        })

    except Watchlist.DoesNotExist:
        return Response({
            'error': 'Watchlist item not found or does not belong to you.'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error removing from watchlist: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_returns_api(request):
    """
    API endpoint to simulate potential returns if following an influencer
    Calculate projected returns based on historical performance
    """
    influencer_id = request.data.get('influencer_id')
    budget = float(request.data.get('budget', 1000))
    period_days = int(request.data.get('period_days', 30))

    if not influencer_id:
        return Response({
            'error': 'influencer_id is required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        from django.utils import timezone
        from datetime import timedelta

        influencer = Influencer.objects.get(influencer_id=influencer_id)

        # Get historical calls within the period
        end_date = timezone.now()
        start_date = end_date - timedelta(days=period_days)

        historical_calls = TradeCall.objects.filter(
            influencer=influencer,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
            status='True',
            target_hit__isnull=False  # Only resolved calls
        )

        total_calls = historical_calls.count()

        if total_calls == 0:
            return Response({
                'error': 'No historical data available for this period.',
                'influencer': {
                    'id': influencer.influencer_id,
                    'channel_name': influencer.channel_name
                }
            }, status=status.HTTP_404_NOT_FOUND)

        # Calculate returns for each successful call
        successful_calls = historical_calls.filter(target_hit=True)
        failed_calls = historical_calls.filter(stoploss_hit=True)

        total_return = budget  # Start with initial budget
        per_call_budget = budget / total_calls  # Equal allocation per call

        returns_data = []
        cumulative_value = budget

        for call in historical_calls.order_by('timestamp'):
            if call.target_hit and call.assumed_entry_price and call.target_first:
                # Calculate return for this call
                entry = call.assumed_entry_price
                target = call.target_first
                return_pct = ((target - entry) / entry)
                call_return = per_call_budget * return_pct
                cumulative_value += call_return

                returns_data.append({
                    'date': call.timestamp.isoformat(),
                    'asset': call.asset.symbol if call.asset else 'Unknown',
                    'signal': call.signal,
                    'entry': entry,
                    'target': target,
                    'return_pct': round(return_pct * 100, 2),
                    'return_amount': round(call_return, 2),
                    'cumulative_value': round(cumulative_value, 2)
                })

            elif call.stoploss_hit and call.assumed_entry_price and call.stoploss_price:
                # Calculate loss for this call
                entry = call.assumed_entry_price
                stoploss = call.stoploss_price
                loss_pct = ((stoploss - entry) / entry)
                call_loss = per_call_budget * loss_pct
                cumulative_value += call_loss

                returns_data.append({
                    'date': call.timestamp.isoformat(),
                    'asset': call.asset.symbol if call.asset else 'Unknown',
                    'signal': call.signal,
                    'entry': entry,
                    'stoploss': stoploss,
                    'return_pct': round(loss_pct * 100, 2),
                    'return_amount': round(call_loss, 2),
                    'cumulative_value': round(cumulative_value, 2)
                })

        # Calculate summary statistics
        final_value = cumulative_value
        total_return_amount = final_value - budget
        total_return_pct = (total_return_amount / budget) * 100

        success_rate = (successful_calls.count() / total_calls * 100) if total_calls > 0 else 0

        # Calculate average return per winning trade
        avg_win = 0
        if successful_calls.count() > 0:
            win_returns = [r['return_amount'] for r in returns_data if r.get('return_amount', 0) > 0]
            if win_returns:
                avg_win = sum(win_returns) / len(win_returns)

        # Calculate average loss per losing trade
        avg_loss = 0
        if failed_calls.count() > 0:
            loss_returns = [r['return_amount'] for r in returns_data if r.get('return_amount', 0) < 0]
            if loss_returns:
                avg_loss = sum(loss_returns) / len(loss_returns)

        simulation_result = {
            'influencer': {
                'id': influencer.influencer_id,
                'channel_name': influencer.channel_name,
                'platform': influencer.platform
            },
            'simulation_parameters': {
                'initial_budget': budget,
                'period_days': period_days,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'results': {
                'final_value': round(final_value, 2),
                'total_return_amount': round(total_return_amount, 2),
                'total_return_pct': round(total_return_pct, 2),
                'total_calls': total_calls,
                'successful_calls': successful_calls.count(),
                'failed_calls': failed_calls.count(),
                'success_rate': round(success_rate, 1),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2)
            },
            'chart_data': returns_data
        }

        return Response(simulation_result)

    except Influencer.DoesNotExist:
        return Response({
            'error': 'Influencer not found.'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error running simulation: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

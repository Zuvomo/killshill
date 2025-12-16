from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
import logging
from django.db.models import (
    Count,
    Q,
    Avg,
    Case,
    When,
    FloatField,
    IntegerField,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
)
from django.db.models.functions import Cast, TruncDate, Coalesce
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.urls import reverse
from influencers.models import Influencer, Asset, TradeCall
from django.utils import timezone
from datetime import timedelta, datetime, time
import json
import asyncio
import math
import statistics
import re
from urllib.parse import urlparse
from authentication.models import UserProfile
from .services.apify_integration import apify_service
from .services.auto_approval_enhanced import enhanced_auto_approval_service
from .services.search_service import perform_influencer_search
from .utils.statistics import clopper_pearson_interval
from .constants import (
    SUPPORTED_SEARCH_PLATFORMS,
    SUPPORTED_SEARCH_CATEGORIES,
    SUPPORTED_PLATFORM_VALUES,
    SUPPORTED_CATEGORY_VALUES,
)
from .models import Watchlist

logger = logging.getLogger(__name__)

SIGNAL_TIMEFRAME_CHOICES = [
    ('7', 'Last 7 days'),
    ('30', 'Last 30 days'),
    ('90', 'Last 90 days'),
    ('180', 'Last 6 months'),
    ('365', 'Last 12 months'),
    ('all', 'All time'),
]


class DashboardHomeView(TemplateView):
    """
    Main dashboard home view - accessible to all users
    """
    template_name = 'dashboard/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Avg, Sum, Q, Case, When, IntegerField, FloatField
        from influencers.models import WebInfluencer, WebInfluencerDetails
        
        # Date ranges for analysis
        now = timezone.now()
        today = now.date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # === CORE TRADING STATISTICS ===
        
        # Total counts - only use valid tracked trade calls (status='True')
        total_influencers = Influencer.objects.count()
        total_trade_calls = TradeCall.objects.filter(status='True').count()
        total_assets = Asset.objects.count()

        # Trading performance metrics - only for valid tracked calls
        successful_calls = TradeCall.objects.filter(status='True', target_hit=True).count()
        failed_calls = TradeCall.objects.filter(status='True', stoploss_hit=True).count()
        total_resolved_calls = successful_calls + failed_calls
        success_rate = round((successful_calls / total_resolved_calls * 100)) if total_resolved_calls > 0 else 0

        # Active vs completed calls - only valid tracked calls
        active_calls = TradeCall.objects.filter(status='True', done=False).count()
        completed_calls = TradeCall.objects.filter(status='True', done=True).count()
        
        context.update({
            'total_influencers': total_influencers,
            'total_trade_calls': total_trade_calls,
            'total_assets': total_assets,
            'success_rate': success_rate,
            'active_calls': active_calls,
            'completed_calls': completed_calls,
            'successful_calls': successful_calls,
            'failed_calls': failed_calls,
        })
        
        # === RECENT TRADING ACTIVITY ===
        
        # Today's calls - only valid tracked calls
        today_calls = TradeCall.objects.filter(status='True', created_at__gte=today_start).count()
        context['today_calls'] = today_calls

        # Weekly performance - only valid tracked calls
        weekly_calls = TradeCall.objects.filter(status='True', created_at__gte=week_ago)
        weekly_successful = weekly_calls.filter(target_hit=True).count()
        weekly_total_resolved = weekly_calls.filter(Q(target_hit=True) | Q(stoploss_hit=True)).count()
        weekly_success_rate = round((weekly_successful / weekly_total_resolved * 100)) if weekly_total_resolved > 0 else 0

        context['weekly_calls'] = weekly_calls.count()
        context['weekly_success_rate'] = weekly_success_rate

        # Last trade call - only valid tracked calls
        last_trade_call = TradeCall.objects.filter(status='True').order_by('-created_at').first()
        context['last_trade_call'] = last_trade_call.created_at if last_trade_call else None
        
        # === TOP INFLUENCERS BY PERFORMANCE ===

        # Calculate influencer performance based on their trade calls - only valid tracked calls (status='True')
        influencer_performance = Influencer.objects.annotate(
            total_calls=Count('tradecall', filter=Q(tradecall__status='True')),
            successful_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__target_hit=True)),
            failed_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__stoploss_hit=True))
        ).filter(total_calls__gt=0).order_by('-total_calls')[:50]

        # Calculate accuracy in Python and create leaderboard preview with categories
        leaderboard_preview = []
        crypto_influencers = []
        stocks_influencers = []
        forex_influencers = []

        for influencer in influencer_performance:
            resolved_calls = influencer.successful_calls + influencer.failed_calls
            if resolved_calls > 0:
                accuracy = round((influencer.successful_calls / resolved_calls) * 100, 1)
            else:
                accuracy = 0

            # Determine category from asset types in their trade calls - only valid tracked calls
            trade_calls_with_assets = TradeCall.objects.filter(
                status='True',
                influencer=influencer
            ).select_related('asset').exclude(asset__isnull=True)[:10]

            category = 'Crypto'  # Default
            category_counts = {'crypto': 0, 'stocks': 0, 'forex': 0}

            for call in trade_calls_with_assets:
                asset_type = call.asset.asset_type.lower() if call.asset and call.asset.asset_type else ''
                if 'stock' in asset_type or 'equity' in asset_type:
                    category_counts['stocks'] += 1
                elif 'forex' in asset_type or 'currency' in asset_type or 'fx' in asset_type:
                    category_counts['forex'] += 1
                else:
                    category_counts['crypto'] += 1

            # Assign category based on majority
            if category_counts['stocks'] > category_counts['crypto'] and category_counts['stocks'] > category_counts['forex']:
                category = 'Stocks'
            elif category_counts['forex'] > category_counts['crypto'] and category_counts['forex'] > category_counts['stocks']:
                category = 'Forex'
            else:
                category = 'Crypto'

            # Conservative confidence using Clopper-Pearson lower bound
            ci_low, ci_high = clopper_pearson_interval(influencer.successful_calls, resolved_calls) if resolved_calls > 0 else (0.0, 0.0)
            confidence_value = ci_low

            influencer_data = {
                'influencer': influencer,
                'accuracy': accuracy,
                'total_calls': influencer.total_calls,
                'risk_reward': round(1.5 + (accuracy / 100) * 2, 1),
                'time_to_target': f"{round(2 + (accuracy / 50), 1)}d",
                'confidence_value': confidence_value,
                'confidence_ci': {
                    'low': ci_low,
                    'high': ci_high,
                },
                'resolved_calls': resolved_calls,
                'category': category
            }

            leaderboard_preview.append(influencer_data)

            # Group by category for trending sections
            if category == 'Crypto' and len(crypto_influencers) < 3:
                crypto_influencers.append(influencer_data)
            elif category == 'Stocks' and len(stocks_influencers) < 3:
                stocks_influencers.append(influencer_data)
            elif category == 'Forex' and len(forex_influencers) < 3:
                forex_influencers.append(influencer_data)

        # Sort by accuracy descending (highest accuracy first)
        leaderboard_preview.sort(key=lambda x: x['accuracy'], reverse=True)
        crypto_influencers.sort(key=lambda x: x['accuracy'], reverse=True)
        stocks_influencers.sort(key=lambda x: x['accuracy'], reverse=True)
        forex_influencers.sort(key=lambda x: x['accuracy'], reverse=True)

        context['top_influencers'] = influencer_performance
        context['leaderboard_preview'] = leaderboard_preview[:10]  # Top 10 for main leaderboard
        context['crypto_influencers'] = crypto_influencers
        context['stocks_influencers'] = stocks_influencers
        context['forex_influencers'] = forex_influencers
        
        # === RECENT TRADE CALLS ===

        # Only show valid tracked trade calls (status='True')
        recent_trade_calls = TradeCall.objects.filter(
            status='True'
        ).select_related(
            'influencer', 'asset'
        ).order_by('-created_at')[:10]
        
        context['recent_trade_calls'] = recent_trade_calls
        
        # === ASSET PERFORMANCE ===
        
        # Most traded assets - only from valid tracked calls
        top_assets = Asset.objects.annotate(
            call_count=Count('tradecall', filter=Q(tradecall__status='True'))
        ).filter(call_count__gt=0).order_by('-call_count')[:5]
        
        context['top_assets'] = top_assets
        
        # === PLATFORM BREAKDOWN ===
        
        # Influencer distribution by platform
        platform_stats = Influencer.objects.values('platform').annotate(
            count=Count('platform'),
            avg_calls=Avg('tradecall__id')
        ).order_by('-count')
        
        context['platform_stats'] = platform_stats
        
        
        # === SUBMISSION STATISTICS FOR QUICK STATS SIDEBAR ===

        from .models import InfluencerSubmission

        # Get submission stats
        auto_approved_today = InfluencerSubmission.objects.filter(
            created_at__gte=today_start,
            auto_approved=True,
            status='approved'
        ).count()

        pending_submissions = InfluencerSubmission.objects.filter(status='pending').count()

        # Calculate approval rate
        total_submissions_count = InfluencerSubmission.objects.count()
        approved_submissions_count = InfluencerSubmission.objects.filter(status='approved').count()
        approval_rate = round((approved_submissions_count / total_submissions_count * 100)) if total_submissions_count > 0 else 0

        # Last processed submission
        last_submission = InfluencerSubmission.objects.filter(
            status__in=['approved', 'rejected']
        ).order_by('-updated_at').first()

        # Calculate time ago for last processed
        last_processed = None
        if last_submission:
            time_diff = now - last_submission.updated_at
            if time_diff.total_seconds() < 60:
                last_processed = f"{int(time_diff.total_seconds())}s ago"
            elif time_diff.total_seconds() < 3600:
                last_processed = f"{int(time_diff.total_seconds() / 60)}m ago"
            elif time_diff.total_seconds() < 86400:
                last_processed = f"{int(time_diff.total_seconds() / 3600)}h ago"
            else:
                last_processed = f"{int(time_diff.total_seconds() / 86400)}d ago"

        context['auto_approved_today'] = auto_approved_today
        context['pending_submissions'] = pending_submissions
        context['approval_rate'] = approval_rate
        context['last_processed'] = last_processed

        # === SIGNALS PREVIEW ===

        # Highlight active signals from influencers with proven accuracy
        active_calls_qs = TradeCall.objects.select_related(
            'influencer', 'asset'
        ).filter(
            Q(done=False) | Q(done__isnull=True),
            Q(target_hit=False) | Q(target_hit__isnull=True),
            Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True),
            status='True',
            asset__isnull=False,
            influencer__isnull=False,
        ).order_by('-created_at')

        active_calls = list(active_calls_qs[:30])
        influencer_ids = {call.influencer_id for call in active_calls if call.influencer_id}

        accuracy_map = {}
        if influencer_ids:
            performance_stats = TradeCall.objects.filter(
                status='True',
                influencer_id__in=influencer_ids
            ).values('influencer_id').annotate(
                successful=Count('id', filter=Q(target_hit=True)),
                failed=Count('id', filter=Q(stoploss_hit=True))
            )
            for stat in performance_stats:
                resolved = stat['successful'] + stat['failed']
                accuracy_map[stat['influencer_id']] = round(
                    (stat['successful'] / resolved) * 100, 1
                ) if resolved > 0 else 0

        def sort_key(call):
            accuracy = accuracy_map.get(call.influencer_id, 0)
            ts = call.created_at or timezone.now()
            # Ensure timezone awareness
            if ts and timezone.is_naive(ts):
                ts = timezone.make_aware(ts)
            return (accuracy, ts)

        active_calls.sort(key=sort_key, reverse=True)
        signals_preview = active_calls[:3]

        def derive_handle(call):
            if not call.influencer:
                return ''
            candidate = ''
            url_value = (call.influencer.url or '').strip()
            if url_value:
                parsed = urlparse(url_value if '://' in url_value else f"https://{url_value}")
                path = parsed.path.strip('/') if parsed.path else ''
                if path:
                    candidate = path.split('/')[-1]
                elif parsed.netloc and 't.me' in parsed.netloc and parsed.path:
                    candidate = parsed.path.strip('/')
            if not candidate and call.influencer.channel_name:
                candidate = call.influencer.channel_name
            if not candidate and call.influencer.author_name:
                candidate = call.influencer.author_name
            candidate = (candidate or '').strip()
            if candidate.startswith('@'):
                candidate = candidate[1:]
            candidate = candidate.replace(' ', '')
            candidate = re.sub(r'[^A-Za-z0-9_.]', '', candidate)
            return candidate.lower()

        signals_data = []
        for call in signals_preview:
            # Determine status based on call data
            if call.target_hit:
                status = 'Hit'
                badge_class = 'success'
            elif call.stoploss_hit:
                status = 'Stopped'
                badge_class = 'danger'
            elif call.done:
                status = 'Closed'
                badge_class = 'secondary'
            else:
                status = 'Active'
                badge_class = 'warning'

            # Calculate time ago
            time_ago_str = 'Just now'
            if call.created_at:
                created_at = call.created_at
                if timezone.is_naive(created_at):
                    created_at = timezone.make_aware(created_at)
                time_diff = now - created_at
                if time_diff.total_seconds() < 60:
                    time_ago_str = f"{int(time_diff.total_seconds())}s ago"
                elif time_diff.total_seconds() < 3600:
                    time_ago_str = f"{int(time_diff.total_seconds() / 60)}m ago"
                elif time_diff.total_seconds() < 86400:
                    time_ago_str = f"{int(time_diff.total_seconds() / 3600)}h ago"
                else:
                    time_ago_str = f"{int(time_diff.total_seconds() / 86400)}d ago"

            # Truncate description/signal text
            # Prioritize 'text' field which contains scraped content
            signal_text = call.text or call.description or call.signal or ''
            if len(signal_text) > 100:
                signal_text = signal_text[:100] + '...'

            signals_data.append({
                'id': call.id,
                'call': call,
                'status': status,
                'badge_class': badge_class,
                'platform': call.influencer.platform if call.influencer else 'Unknown',
                'time_ago': time_ago_str,
                'signal_text': signal_text,
                'asset_symbol': call.asset.symbol if call.asset else 'N/A',
                'influencer_name': call.influencer.channel_name if call.influencer else 'Unknown',
                'influencer_handle': derive_handle(call),
                'accuracy': accuracy_map.get(call.influencer_id, 0)
            })

        context['signals_preview'] = signals_data
        
        # === TIME-BASED ACTIVITY ===
        
        # Trade calls by day (last 7 days)
        daily_calls = []
        for i in range(7):
            day = today - timedelta(days=i)
            day_start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
            day_end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.max.time()))
            
            day_count = TradeCall.objects.filter(
                status='True',
                created_at__range=[day_start, day_end]
            ).count()
            
            daily_calls.append({
                'date': day.strftime('%m/%d'),
                'count': day_count
            })
        
        context['daily_calls'] = list(reversed(daily_calls))
        
        # === JSON SERIALIZATION FOR JAVASCRIPT ===
        import json
        
        # Serialize data for JavaScript charts
        context['daily_calls_json'] = json.dumps(context['daily_calls'])
        
        # Platform stats for chart
        platform_stats_for_chart = []
        for stat in platform_stats:
            platform_stats_for_chart.append({
                'platform': stat['platform'] or 'Unknown',
                'count': stat['count']
            })
        context['platform_stats_json'] = json.dumps(platform_stats_for_chart)
        
        return context


class LeaderboardView(TemplateView):
    """
    KOL Leaderboard view - accessible to all users
    """
    template_name = 'dashboard/leaderboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.db.models import Count, Avg, Case, When, FloatField, Q, Max, Min, Sum
        from datetime import timedelta
        from decimal import Decimal

        # Get filter parameters (normalize category/timeframe for consistent comparisons)
        category = (self.request.GET.get('category') or 'all').lower()
        platform = self.request.GET.get('platform', 'all')
        timeframe_param = self.request.GET.get('timeframe', '30')

        # Validate timeframe parameter
        cutoff_date = None
        if timeframe_param != 'all':
            try:
                days = int(timeframe_param)
            except (TypeError, ValueError):
                days = 30
                timeframe_param = '30'
            cutoff_date = timezone.now() - timedelta(days=days)

        context['selected_category'] = category
        context['selected_platform'] = platform
        context['selected_timeframe'] = timeframe_param

        # Build reusable filters for annotations
        base_call_filter = Q(tradecall__status='True')
        if cutoff_date:
            base_call_filter &= Q(tradecall__created_at__gte=cutoff_date)

        success_filter = base_call_filter & Q(tradecall__target_hit=True)
        failure_filter = base_call_filter & Q(tradecall__stoploss_hit=True)

        # Build base query for influencers with trade calls - only valid tracked calls (status='True')
        influencer_query = Influencer.objects.all()

        if platform and platform != 'all':
            influencer_query = influencer_query.filter(platform__icontains=platform)

        influencer_query = influencer_query.annotate(
            total_calls=Count('tradecall', filter=base_call_filter),
            successful_calls=Count('tradecall', filter=success_filter),
            failed_calls=Count('tradecall', filter=failure_filter)
        ).filter(total_calls__gt=0)

        # Get top influencers ordered by total calls first, then we'll calculate accuracy
        influencers = influencer_query.order_by('-total_calls')[:100]

        # Enhance data with additional metrics
        influencers_data = []
        for i, influencer in enumerate(influencers):
            total_calls = influencer.total_calls or 0
            successful_calls = influencer.successful_calls or 0
            failed_calls = influencer.failed_calls or 0

            # Calculate accuracy in Python
            resolved_calls = successful_calls + failed_calls
            if resolved_calls > 0:
                accuracy = round((successful_calls / resolved_calls) * 100, 1)
            else:
                accuracy = 0

            # Base filter for trade calls tied to this influencer respecting timeframe
            influencer_call_filter = Q(status='True', influencer=influencer)
            if cutoff_date:
                influencer_call_filter &= Q(created_at__gte=cutoff_date)

            # Calculate actual metrics from trade calls (respect filters)
            trade_calls_resolved = TradeCall.objects.filter(
                influencer_call_filter,
                done=True
            ).select_related('asset')

            # Calculate median risk:reward ratio from actual calls
            rr_ratios = []
            time_to_targets = []

            for call in trade_calls_resolved:
                if call.target_hit and call.assumed_entry_price and call.assumed_target and call.stoploss_price:
                    try:
                        profit = call.assumed_target - call.assumed_entry_price
                        risk = call.assumed_entry_price - call.stoploss_price
                        if risk > 0:
                            rr_ratios.append(profit / risk)
                    except (TypeError, ValueError):
                        continue

                # Calculate time to target for successful calls
                if call.target_hit and call.created_at and call.timeframe:
                    try:
                        # Make both datetimes timezone-aware
                        from django.utils import timezone as tz
                        created_at = call.created_at
                        call_timeframe = call.timeframe

                        # Ensure both are timezone-aware
                        if created_at and not tz.is_aware(created_at):
                            created_at = tz.make_aware(created_at)
                        if call_timeframe and not tz.is_aware(call_timeframe):
                            call_timeframe = tz.make_aware(call_timeframe)

                        if created_at and call_timeframe:
                            time_diff = call_timeframe - created_at
                            days = time_diff.total_seconds() / (24 * 3600)
                            if days > 0:
                                time_to_targets.append(days)
                    except (TypeError, ValueError, AttributeError):
                        continue

            # Calculate medians
            if rr_ratios:
                rr_ratios.sort()
                median_rr = round(rr_ratios[len(rr_ratios) // 2], 1)
            else:
                median_rr = round(1.5 + (accuracy / 100) * 2, 1)  # Fallback calculation

            if time_to_targets:
                time_to_targets.sort()
                median_tt_days = time_to_targets[len(time_to_targets) // 2]
                median_tt = f"{round(median_tt_days, 1)}d"
            else:
                median_tt = f"{round(2 + (accuracy / 50), 1)}d"  # Fallback

            # Confidence score using Clopper-Pearson interval (95% CI) - show conservative lower bound
            ci_low, ci_high = clopper_pearson_interval(successful_calls, resolved_calls) if resolved_calls > 0 else (0.0, 0.0)
            confidence_value = ci_low

            # Determine category from asset types in their trade calls - only valid tracked calls
            trade_calls_with_assets = TradeCall.objects.filter(
                influencer_call_filter
            ).select_related('asset').exclude(asset__isnull=True)[:20]

            influencer_category = 'Crypto'  # Default
            category_counts = {'crypto': 0, 'stocks': 0, 'forex': 0, 'commodities': 0}

            for call in trade_calls_with_assets:
                asset_type = call.asset.asset_type.lower() if call.asset and call.asset.asset_type else ''
                if 'stock' in asset_type or 'equity' in asset_type:
                    category_counts['stocks'] += 1
                elif 'forex' in asset_type or 'currency' in asset_type or 'fx' in asset_type:
                    category_counts['forex'] += 1
                elif 'commodit' in asset_type or 'gold' in asset_type or 'oil' in asset_type:
                    category_counts['commodities'] += 1
                else:
                    category_counts['crypto'] += 1

            # Assign category based on majority
            max_category = max(category_counts, key=category_counts.get)
            if category_counts[max_category] > 0:
                influencer_category = max_category.capitalize()

            # Apply category filter if specified
            if category != 'all' and category != influencer_category.lower():
                continue

            # Get platform info - handle multiple platforms from influencer data
            platforms = []
            if influencer.platform:
                # Clean and normalize platform name
                platform_name = influencer.platform.strip()
                if platform_name:
                    platforms.append(platform_name)

            if not platforms:
                platforms = ['Web']  # Default fallback

            influencer_data = {
                'rank': i + 1,
                'influencer': influencer,
                'accuracy': accuracy,
                'success_rate': accuracy,  # Alias for template compatibility
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'resolved_calls': resolved_calls,
                'median_rr': median_rr,
                'median_tt': median_tt,
                'confidence_value': confidence_value,
                'confidence_ci': {
                    'low': ci_low,
                    'high': ci_high,
                },
                'category': influencer_category,
                'platforms': platforms,
            }
            influencers_data.append(influencer_data)

        # Sort by accuracy descending (highest accuracy first), then by total calls
        influencers_data.sort(key=lambda x: (x['accuracy'], x['total_calls']), reverse=True)

        # Update ranks after sorting
        for idx, inf in enumerate(influencers_data, 1):
            inf['rank'] = idx

        # Calculate statistics for the stats cards
        if influencers_data:
            top_accuracy = influencers_data[0]['accuracy']
            total_calls_sum = sum(inf['total_calls'] for inf in influencers_data)

            # Calculate average time to target (convert back to days)
            avg_days_list = []
            for inf in influencers_data:
                tt_str = inf['median_tt']
                if tt_str and 'd' in tt_str:
                    try:
                        days = float(tt_str.replace('d', ''))
                        avg_days_list.append(days)
                    except:
                        pass
            avg_time_to_target = f"{round(sum(avg_days_list) / len(avg_days_list), 1)}d" if avg_days_list else "2.4d"
        else:
            top_accuracy = 0
            total_calls_sum = 0
            avg_time_to_target = "N/A"

        context['top_accuracy'] = top_accuracy
        context['total_calls_sum'] = total_calls_sum
        context['avg_time_to_target'] = avg_time_to_target

        # Pagination
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

        page_number = self.request.GET.get('page', 1)
        paginator = Paginator(influencers_data, 20)  # 20 items per page

        try:
            paginated_influencers = paginator.page(page_number)
        except PageNotAnInteger:
            paginated_influencers = paginator.page(1)
        except EmptyPage:
            paginated_influencers = paginator.page(paginator.num_pages)

        context['influencers'] = paginated_influencers
        context['paginator'] = paginator
        context['page_obj'] = paginated_influencers
        context['total_influencers'] = len(influencers_data)

        # Available platforms for filter
        context['platforms'] = ['Twitter', 'YouTube', 'TikTok', 'Telegram', 'Discord', 'Instagram']
        context['categories'] = ['Crypto', 'Stocks', 'Forex', 'Commodities']

        return context


class SignalsView(LoginRequiredMixin, TemplateView):
    """
    Detailed signals log with filters/pagination
    """
    template_name = 'dashboard/signals.html'
    page_size = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        platform = (self.request.GET.get('platform') or '').strip()
        status_filter = (self.request.GET.get('status') or '').strip().lower()
        timeframe = (self.request.GET.get('timeframe') or '30').strip() or '30'
        query = (self.request.GET.get('query') or '').strip()
        limit = self._parse_limit(self.request.GET.get('limit'))

        signals_qs = TradeCall.objects.select_related('influencer', 'asset').filter(status='True')

        cutoff = None
        if timeframe != 'all':
            try:
                days = max(1, int(timeframe))
                cutoff = timezone.now() - timedelta(days=days)
            except (TypeError, ValueError):
                timeframe = '30'
                cutoff = timezone.now() - timedelta(days=30)
        if cutoff:
            signals_qs = signals_qs.filter(created_at__gte=cutoff)

        if platform:
            signals_qs = signals_qs.filter(influencer__platform__icontains=platform)

        if query:
            signals_qs = signals_qs.filter(
                Q(influencer__channel_name__icontains=query) |
                Q(influencer__author_name__icontains=query) |
                Q(asset__symbol__icontains=query) |
                Q(asset__name__icontains=query) |
                Q(signal__icontains=query) |
                Q(description__icontains=query)
            )

        summary_qs = signals_qs
        summary = {
            'total': summary_qs.count(),
            'hit': summary_qs.filter(target_hit=True).count(),
            'stopped': summary_qs.filter(stoploss_hit=True).count(),
            'active': summary_qs.filter(
                (Q(done=False) | Q(done__isnull=True)),
                Q(target_hit=False) | Q(target_hit__isnull=True),
                Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True)
            ).count(),
        }

        if status_filter == 'hit':
            signals_qs = signals_qs.filter(target_hit=True)
        elif status_filter == 'stopped':
            signals_qs = signals_qs.filter(stoploss_hit=True)
        elif status_filter == 'active':
            signals_qs = signals_qs.filter(
                (Q(done=False) | Q(done__isnull=True)),
                Q(target_hit=False) | Q(target_hit__isnull=True),
                Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True)
            )

        total_filtered = signals_qs.count()
        signals = list(signals_qs.order_by('-created_at')[:limit])

        context.update({
            'signals': signals,
            'summary': summary,
            'selected_platform': platform,
            'selected_status': status_filter,
            'selected_timeframe': timeframe,
            'platform_choices': SUPPORTED_SEARCH_PLATFORMS,
            'timeframe_choices': SIGNAL_TIMEFRAME_CHOICES,
            'query': query,
            'more_signals': total_filtered > limit,
            'next_limit': limit + self.page_size,
        })

        return context

    def _parse_limit(self, raw_limit):
        try:
            value = int(raw_limit)
        except (TypeError, ValueError):
            value = self.page_size
        return max(self.page_size, min(250, value))


class TrendingKOLsView(TemplateView):
    """
    Trending KOLs view - accessible to all users
    """
    template_name = 'dashboard/trending_kols.html'

    timeframe_map = {
        '24h': 1,
        '7d': 7,
        '30d': 30,
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        timeframe = self.request.GET.get('timeframe', '7d')
        days = self.timeframe_map.get(timeframe, 7)

        cutoff = timezone.now() - timedelta(days=days)
        prev_cutoff = cutoff - timedelta(days=days)

        recent_calls = TradeCall.objects.filter(
            status='True',
            influencer__isnull=False,
            created_at__gte=cutoff
        )

        prev_calls = TradeCall.objects.filter(
            status='True',
            influencer__isnull=False,
            created_at__gte=prev_cutoff,
            created_at__lt=cutoff
        )

        recent_stats = recent_calls.values(
            'influencer_id',
            'influencer__channel_name',
            'influencer__author_name',
            'influencer__platform'
        ).annotate(
            total_calls=Count('id'),
            wins=Count('id', filter=Q(target_hit=True)),
            losses=Count('id', filter=Q(stoploss_hit=True)),
        )

        prev_stats = prev_calls.values('influencer_id').annotate(
            total_calls=Count('id'),
            wins=Count('id', filter=Q(target_hit=True)),
            losses=Count('id', filter=Q(stoploss_hit=True)),
        )
        prev_map = {row['influencer_id']: row for row in prev_stats}

        trending = []
        for row in recent_stats:
            resolved = row['wins'] + row['losses']
            accuracy = round((row['wins'] / resolved) * 100, 1) if resolved > 0 else 0

            prev = prev_map.get(row['influencer_id'])
            if prev:
                prev_resolved = prev['wins'] + prev['losses']
                prev_accuracy = round((prev['wins'] / prev_resolved) * 100, 1) if prev_resolved > 0 else 0
                trend_delta = round(accuracy - prev_accuracy, 1)
                call_delta = row['total_calls'] - prev['total_calls']
            else:
                prev_accuracy = 0
                trend_delta = accuracy
                call_delta = row['total_calls']

            trend_label = 'up' if trend_delta > 0 else 'down' if trend_delta < 0 else 'flat'

            trending.append({
                'influencer_id': row['influencer_id'],
                'name': row['influencer__channel_name'] or row['influencer__author_name'] or 'Unknown',
                'handle': row['influencer__author_name'] or '',
                'platform': row['influencer__platform'] or 'Unknown',
                'accuracy': accuracy,
                'calls': row['total_calls'],
                'wins': row['wins'],
                'losses': row['losses'],
                'trend_delta': trend_delta,
                'call_delta': call_delta,
                'trend_label': trend_label,
            })

        trending.sort(key=lambda item: (item['accuracy'], item['trend_delta'], item['calls']), reverse=True)
        top_trending = trending[:5]

        rising_stars = [item for item in trending if item['trend_delta'] > 0]
        rising_stars.sort(key=lambda item: (item['trend_delta'], item['accuracy']), reverse=True)
        rising_stars = rising_stars[:5]

        highlight_cards = {
            'hottest': top_trending[0] if top_trending else None,
            'active': max(trending, key=lambda item: item['calls']) if trending else None,
            'rising': rising_stars[0] if rising_stars else None
        }

        platform_stats = recent_calls.values('influencer__platform').annotate(
            calls=Count('id'),
            wins=Count('id', filter=Q(target_hit=True)),
            losses=Count('id', filter=Q(stoploss_hit=True))
        )
        platform_cards = []
        for stat in platform_stats:
            resolved = stat['wins'] + stat['losses']
            accuracy = round((stat['wins'] / resolved) * 100, 1) if resolved > 0 else 0
            platform_cards.append({
                'platform': stat['influencer__platform'] or 'Unknown',
                'accuracy': accuracy,
                'calls': stat['calls']
            })
        platform_cards.sort(key=lambda item: item['calls'], reverse=True)
        platform_cards = platform_cards[:4]

        context.update({
            'selected_timeframe': timeframe,
            'top_trending': top_trending,
            'rising_stars': rising_stars,
            'highlight_cards': highlight_cards,
            'platform_cards': platform_cards,
        })

        return context


class AnalyticsView(TemplateView):
    """
    Analytics dashboard view - accessible to all users
    """
    template_name = 'dashboard/analytics.html'

    def get(self, request, *args, **kwargs):
        if request.GET.get('embed') == '1':
            context = self.get_context_data()
            return render(request, 'dashboard/analytics_embed.html', context)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.db.models import Count, Q
        from datetime import timedelta

        # Get timeframe from request (default: 30 days)
        timeframe_param = self.request.GET.get('timeframe', '30d')
        if timeframe_param == '7d':
            days = 7
        elif timeframe_param == '90d':
            days = 90
        elif timeframe_param == '1y':
            days = 365
        else:
            days = 30  # default

        cutoff_date = timezone.now() - timedelta(days=days)

        # Get trade calls within timeframe
        trade_calls = TradeCall.objects.filter(
            status='True',
            created_at__gte=cutoff_date
        )

        # Overall success rate
        total_resolved = trade_calls.filter(Q(target_hit=True) | Q(stoploss_hit=True)).count()
        successful = trade_calls.filter(target_hit=True).count()
        success_rate = round((successful / total_resolved * 100), 1) if total_resolved > 0 else 0

        # Previous period comparison
        prev_cutoff = cutoff_date - timedelta(days=days)
        prev_calls = TradeCall.objects.filter(
            status='True',
            created_at__gte=prev_cutoff,
            created_at__lt=cutoff_date
        )
        prev_resolved = prev_calls.filter(Q(target_hit=True) | Q(stoploss_hit=True)).count()
        prev_successful = prev_calls.filter(target_hit=True).count()
        prev_success_rate = (prev_successful / prev_resolved * 100) if prev_resolved > 0 else 0
        success_rate_change = round(success_rate - prev_success_rate, 1)

        # Total signals analyzed
        total_signals = trade_calls.count()

        # Active influencers
        active_influencers = trade_calls.values('influencer').distinct().count()

        # Top categories
        category_stats = {}
        for asset_type in ['crypto', 'stocks', 'forex']:
            cat_calls = trade_calls.filter(asset__asset_type__iexact=asset_type)
            cat_resolved = cat_calls.filter(Q(target_hit=True) | Q(stoploss_hit=True)).count()
            cat_successful = cat_calls.filter(target_hit=True).count()
            cat_accuracy = round((cat_successful / cat_resolved * 100), 1) if cat_resolved > 0 else 0
            category_stats[asset_type] = {
                'total': cat_calls.count(),
                'accuracy': cat_accuracy
            }

        context['success_rate'] = success_rate
        context['success_rate_change'] = success_rate_change
        context['total_signals'] = total_signals
        context['active_influencers'] = active_influencers
        context['category_stats'] = category_stats
        context['timeframe'] = timeframe_param

        # Active signals
        active_signals = trade_calls.filter(
            Q(done=False) | Q(done__isnull=True),
            Q(target_hit=False) | Q(target_hit__isnull=True),
            Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True)
        ).count()
        context['active_signals'] = active_signals

        # Average risk/reward
        rr_values = []
        rr_calls = trade_calls.filter(
            target_hit=True,
            assumed_entry_price__gt=0,
            stoploss_price__gt=0,
            target_first__gt=0
        )
        for call in rr_calls:
            reward = abs(call.target_first - call.assumed_entry_price)
            risk = abs(call.assumed_entry_price - call.stoploss_price)
            if risk > 0:
                rr_values.append(reward / risk)
        context['avg_risk_reward'] = round(sum(rr_values) / len(rr_values), 2) if rr_values else 0

        # Top performers
        influencers_qs = Influencer.objects.annotate(
            total_calls=Count('tradecall', filter=Q(
                tradecall__status='True',
                tradecall__created_at__gte=cutoff_date
            )),
            successful_calls=Count('tradecall', filter=Q(
                tradecall__status='True',
                tradecall__target_hit=True,
                tradecall__created_at__gte=cutoff_date
            )),
            failed_calls=Count('tradecall', filter=Q(
                tradecall__status='True',
                tradecall__stoploss_hit=True,
                tradecall__created_at__gte=cutoff_date
            ))
        ).filter(total_calls__gte=5).order_by('-successful_calls')[:10]

        top_performers = []
        for rank, influencer in enumerate(influencers_qs, start=1):
            resolved = influencer.successful_calls + influencer.failed_calls
            accuracy = round((influencer.successful_calls / resolved) * 100, 1) if resolved > 0 else 0

            # Compute influencer specific RR
            influencer_rr_values = []
            influencer_rr_calls = TradeCall.objects.filter(
                status='True',
                created_at__gte=cutoff_date,
                influencer=influencer,
                target_hit=True,
                assumed_entry_price__gt=0,
                stoploss_price__gt=0,
                target_first__gt=0
            )
            for call in influencer_rr_calls:
                reward = abs(call.target_first - call.assumed_entry_price)
                risk = abs(call.assumed_entry_price - call.stoploss_price)
                if risk > 0:
                    influencer_rr_values.append(reward / risk)
            avg_rr_influencer = round(sum(influencer_rr_values) / len(influencer_rr_values), 2) if influencer_rr_values else 0

            reliability = round((resolved / influencer.total_calls) * 100, 1) if influencer.total_calls else 0

            top_performers.append({
                'rank': rank,
                'name': influencer.channel_name or 'Unknown',
                'handle': influencer.author_name or '',
                'platform': influencer.platform or 'Unknown',
                'accuracy': accuracy,
                'total_calls': influencer.total_calls,
                'wins': influencer.successful_calls,
                'losses': influencer.failed_calls,
                'avg_rr': avg_rr_influencer,
                'reliability': reliability,
            })

        context['top_performers'] = top_performers
        if top_performers:
            context['best_performer'] = top_performers[0]

        # Performance trend (last up to 14 days)
        trend_points = []
        days_range = min(days, 14)
        for offset in reversed(range(days_range)):
            day = timezone.now() - timedelta(days=offset)
            day_date = day.date()
            day_start = timezone.make_aware(datetime.combine(day_date, time.min))
            day_end = timezone.make_aware(datetime.combine(day_date, time.max))
            day_calls = TradeCall.objects.filter(
                status='True',
                created_at__range=[day_start, day_end]
            )
            day_resolved = day_calls.filter(Q(target_hit=True) | Q(stoploss_hit=True)).count()
            day_success = day_calls.filter(target_hit=True).count()
            day_success_rate = round((day_success / day_resolved) * 100, 1) if day_resolved > 0 else 0
            trend_points.append({
                'label': day.strftime('%b %d'),
                'success_rate': day_success_rate,
                'calls': day_calls.count()
            })
        context['trend_chart_data'] = trend_points

        platform_stats = trade_calls.values('influencer__platform').annotate(
            count=Count('id')
        ).order_by('-count')[:6]
        context['platform_chart_data'] = [
            {
                'label': stat['influencer__platform'] or 'Unknown',
                'count': stat['count']
            }
            for stat in platform_stats
        ]

        context['category_chart_data'] = [
            {
                'label': label.title(),
                'accuracy': data['accuracy'],
                'total': data['total']
            }
            for label, data in category_stats.items()
        ]
        context['embed_mode'] = self.request.GET.get('embed') == '1'

        return context


class InsightsDashboardView(TemplateView):
    """
    Deep insights dashboard with consensus, speed leaders, heatmap, and risk analysis
    """
    template_name = 'dashboard/insights.html'

    def get(self, request, *args, **kwargs):
        if request.GET.get('embed') == '1':
            context = self.get_context_data()
            return render(request, 'dashboard/insights_embed.html', context)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        period_start = now - timedelta(days=30)
        base_calls = TradeCall.objects.filter(
            status='True',
            created_at__gte=period_start,
            asset__isnull=False
        )
        period_start_90 = now - timedelta(days=90)
        extended_calls = TradeCall.objects.filter(
            status='True',
            created_at__gte=period_start_90,
            asset__isnull=False
        )

        active_signals = base_calls.filter(
            Q(done=False) | Q(done__isnull=True),
            Q(target_hit=False) | Q(target_hit__isnull=True),
            Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True)
        ).count()

        consensus_data = self._build_consensus_index(base_calls)
        speed_data = self._build_speed_leaders(period_start)
        heatmap_data = self._build_asset_heatmap(base_calls)
        risk_data = self._build_risk_analysis(base_calls, extended_calls)

        context.update(consensus_data)
        context.update(speed_data)
        context.update(heatmap_data)
        context.update(risk_data)
        context['insights_last_updated'] = now
        context['active_signals'] = active_signals
        context['embed_mode'] = self.request.GET.get('embed') == '1'
        return context

    def _build_consensus_index(self, calls_qs):
        consensus_raw = calls_qs.values(
            'asset__symbol',
            'asset__name'
        ).annotate(
            total_calls=Count('id'),
            successes=Count('id', filter=Q(target_hit=True)),
            failures=Count('id', filter=Q(stoploss_hit=True)),
            latest_price=Max('asset__current_price'),
        ).order_by('-total_calls')[:4]

        assets = []
        win_rates = []
        for record in consensus_raw:
            resolved = record['successes'] + record['failures']
            win_rate = round((record['successes'] / resolved) * 100, 1) if resolved else 0
            win_rates.append(win_rate)
            trend_direction = 'up' if record['successes'] >= record['failures'] else 'down'
            assets.append({
                'symbol': record['asset__symbol'],
                'name': record['asset__name'] or record['asset__symbol'],
                'win_rate': win_rate,
                'total_calls': record['total_calls'],
                'price': record['latest_price'],
                'trend': trend_direction,
                'trend_change': round(win_rate - 50, 1)
            })

        consensus_score = round(sum(win_rates) / len(win_rates), 1) if win_rates else 0
        return {
            'consensus_assets': assets,
            'consensus_score': consensus_score,
        }

    def _build_speed_leaders(self, period_start):
        duration_expr = ExpressionWrapper(
            F('timeframe') - F('created_at'),
            output_field=DurationField()
        )
        speed_qs = TradeCall.objects.filter(
            status='True',
            created_at__gte=period_start,
            timeframe__isnull=False,
            influencer__isnull=False,
            target_hit=True,
            timeframe__gt=F('created_at')
        ).values(
            'influencer_id',
            'influencer__channel_name',
            'influencer__platform'
        ).annotate(
            avg_duration=Avg(duration_expr),
            call_count=Count('id')
        ).order_by('avg_duration')[:5]

        leaders = []
        for rank, record in enumerate(speed_qs, start=1):
            avg_timedelta = record['avg_duration']
            avg_hours = (avg_timedelta.total_seconds() / 3600) if avg_timedelta else None
            leaders.append({
                'rank': rank,
                'name': record['influencer__channel_name'] or 'Unknown',
                'platform': record['influencer__platform'] or 'N/A',
                'avg_hours': avg_hours,
                'avg_days': round(avg_hours / 24, 1) if avg_hours else None,
                'call_count': record['call_count'],
                'category': self._classify_platform(record['influencer__platform'])
            })

        return {'speed_leaders': leaders}

    def _build_asset_heatmap(self, calls_qs):
        heatmap_raw = calls_qs.filter(
            asset__asset_type__isnull=False
        ).values(
            'asset__asset_type'
        ).annotate(
            total_calls=Count('id'),
            successes=Count('id', filter=Q(target_hit=True)),
            failures=Count('id', filter=Q(stoploss_hit=True)),
            avg_entry=Avg('assumed_entry_price'),
            avg_target=Avg('target_first'),
            avg_stop=Avg('stoploss_price'),
        ).order_by('-total_calls')[:3]

        heatmap_cards = []
        for record in heatmap_raw:
            resolved = record['successes'] + record['failures']
            win_rate = round((record['successes'] / resolved) * 100, 1) if resolved else 0
            rr_value = self._calculate_risk_reward(
                record['avg_entry'],
                record['avg_target'],
                record['avg_stop']
            )
            heatmap_cards.append({
                'asset_type': record['asset__asset_type'].title(),
                'win_rate': win_rate,
                'total_calls': record['total_calls'],
                'avg_rr': rr_value,
            })

        return {'heatmap_cards': heatmap_cards}

    def _build_risk_analysis(self, calls_qs, extended_calls):
        risk_values = []
        stoploss_entries = calls_qs.exclude(stoploss_percentage__isnull=True).values_list('stoploss_percentage', flat=True)
        for value in stoploss_entries:
            parsed = self._parse_percentage(value)
            if parsed is not None:
                risk_values.append(parsed)

        buckets = {'conservative': 0, 'moderate': 0, 'aggressive': 0}
        for val in risk_values:
            if val <= 2:
                buckets['conservative'] += 1
            elif val <= 5:
                buckets['moderate'] += 1
            else:
                buckets['aggressive'] += 1
        total_risk = sum(buckets.values()) or 1
        risk_distribution = [
            {'label': 'Conservative (1-2% risk)', 'value': round(buckets['conservative'] / total_risk * 100, 1), 'color': 'success'},
            {'label': 'Moderate (2-5% risk)', 'value': round(buckets['moderate'] / total_risk * 100, 1), 'color': 'warning'},
            {'label': 'Aggressive (5%+ risk)', 'value': round(buckets['aggressive'] / total_risk * 100, 1), 'color': 'danger'},
        ]

        volatility_index = 50
        trend_label = 'Stable'
        volatility_avg_30 = round(statistics.mean(risk_values), 1) if risk_values else None
        std_dev = 0
        if risk_values:
            std_dev = statistics.pstdev(risk_values) if len(risk_values) > 1 else 0
            volatility_index = round(min(100, max(0, 45 + std_dev * 5)), 1)
            trend_label = 'Increasing' if std_dev > 1.5 else ('Elevated' if std_dev > 1 else 'Stable')

        extended_risk_values = []
        if extended_calls is not None:
            extended_entries = extended_calls.exclude(stoploss_percentage__isnull=True).values_list('stoploss_percentage', flat=True)
            for value in extended_entries:
                parsed = self._parse_percentage(value)
                if parsed is not None:
                    extended_risk_values.append(parsed)
        volatility_avg_90 = round(statistics.mean(extended_risk_values), 1) if extended_risk_values else None

        consensus_assets = calls_qs.values('asset__symbol').annotate(
            total_calls=Count('id'),
            successes=Count('id', filter=Q(target_hit=True)),
            failures=Count('id', filter=Q(stoploss_hit=True))
        ).order_by('-total_calls')[:4]

        correlation_matrix = self._build_correlation_matrix(consensus_assets, calls_qs)

        return {
            'risk_distribution': risk_distribution,
            'volatility_index': volatility_index,
            'volatility_trend': trend_label,
            'volatility_avg_30': volatility_avg_30,
            'volatility_avg_90': volatility_avg_90,
            'correlation_matrix': correlation_matrix,
        }

    def _parse_percentage(self, value):
        if value is None:
            return None
        try:
            clean = str(value).replace('%', '').strip()
            return float(clean)
        except ValueError:
            return None

    def _calculate_risk_reward(self, entry, target, stoploss):
        if not entry or not target or not stoploss:
            return None
        risk = abs(entry - stoploss)
        reward = abs(target - entry)
        if risk == 0:
            return None
        return round(reward / risk, 1)

    def _classify_platform(self, platform):
        if not platform:
            return ''
        platform = platform.lower()
        if 'stock' in platform:
            return 'Stocks'
        if 'forex' in platform or 'fx' in platform:
            return 'Forex'
        return 'Crypto'

    def _build_correlation_matrix(self, asset_records, calls_qs):
        from collections import defaultdict

        asset_symbols = [record['asset__symbol'] for record in asset_records if record['asset__symbol']]
        if not asset_symbols:
            return []

        daily_stats = calls_qs.filter(asset__symbol__in=asset_symbols).annotate(
            day=TruncDate('created_at')
        ).values(
            'asset__symbol',
            'day'
        ).annotate(
            successes=Count('id', filter=Q(target_hit=True)),
            failures=Count('id', filter=Q(stoploss_hit=True))
        )

        series = defaultdict(dict)
        for entry in daily_stats:
            resolved = entry['successes'] + entry['failures']
            if resolved == 0:
                continue
            rate = entry['successes'] / resolved
            series[entry['asset__symbol']][entry['day']] = rate

        matrix = []
        for symbol_a in asset_symbols:
            row = {'asset': symbol_a}
            for symbol_b in asset_symbols:
                key = f'{symbol_a}_{symbol_b}'
                row[symbol_b] = self._correlate_series(series.get(symbol_a), series.get(symbol_b))
            matrix.append(row)
        return matrix

    def _correlate_series(self, series_a, series_b):
        if not series_a or not series_b:
            return 0
        shared_dates = sorted(set(series_a.keys()) & set(series_b.keys()))
        if len(shared_dates) < 2:
            return 0
        values_a = [series_a[date] for date in shared_dates]
        values_b = [series_b[date] for date in shared_dates]
        mean_a = sum(values_a) / len(values_a)
        mean_b = sum(values_b) / len(values_b)
        numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
        denom_a = math.sqrt(sum((a - mean_a) ** 2 for a in values_a))
        denom_b = math.sqrt(sum((b - mean_b) ** 2 for b in values_b))
        if denom_a == 0 or denom_b == 0:
            return 0
        return round(numerator / (denom_a * denom_b), 2)


class SearchView(TemplateView):
    template_name = 'dashboard/search.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        query = self.request.GET.get('q', '')
        platform = self.request.GET.get('platform', '')
        category = self.request.GET.get('category', '')
        sort_by = self.request.GET.get('sort', 'relevance')

        payload = perform_influencer_search(
            query=query,
            platform=platform,
            category=category,
            sort_by=sort_by,
            page=self.request.GET.get('page', 1),
            page_size=12,
        )
        start_index = 0
        end_index = 0
        if payload.get('results'):
            start_index = ((payload.get('page', 1) - 1) * payload.get('page_size', 12)) + 1
            end_index = start_index + len(payload['results']) - 1

        context.update({
            'query': query,
            'selected_platform': platform,
            'selected_category': category,
            'sort_by': sort_by,
            'search_platform_choices': SUPPORTED_SEARCH_PLATFORMS,
            'search_category_choices': SUPPORTED_SEARCH_CATEGORIES,
            'initial_search_payload': payload,
            'initial_result_window': {
                'start': start_index,
                'end': end_index,
            },
            'search_stats': self._build_search_stats(),
        })

        return context

    def _build_search_stats(self):
        total_influencers = Influencer.objects.count()
        total_trade_calls = TradeCall.objects.filter(status='True').count()
        active_calls = TradeCall.objects.filter(status='True', done=False).count()
        successful = TradeCall.objects.filter(status='True', target_hit=True).count()
        failed = TradeCall.objects.filter(status='True', stoploss_hit=True).count()
        resolved = successful + failed
        success_rate = round((successful / resolved) * 100) if resolved else 0

        return {
            'total_influencers': total_influencers,
            'total_trade_calls': total_trade_calls,
            'active_calls': active_calls,
            'success_rate': success_rate,
        }


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self._get_profile()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', 'profile')
        profile = self._get_profile(create=True)

        if action == 'notifications':
            if profile:
                profile.email_notifications = 'email_notifications' in request.POST
                profile.push_notifications = 'push_notifications' in request.POST
                profile.newsletter_subscription = 'newsletter_subscription' in request.POST
                profile.save()
                messages.success(request, 'Notification preferences updated.')
            else:
                messages.error(request, 'Profile not found. Please try again.')
        elif action == 'password':
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password updated successfully.')
        elif action == 'delete_account':
            confirmation = request.POST.get('delete_confirmation', '').strip().upper()
            current_password = request.POST.get('current_password_delete', '')
            
            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif confirmation != 'DELETE':
                messages.error(request, 'Please type DELETE to confirm account deletion.')
            else:
                try:
                    # Delete user profile if exists
                    if profile:
                        profile.delete()
                    
                    # Delete the user account
                    user = request.user
                    logout(request)
                    user.delete()
                    
                    messages.success(request, 'Your account has been successfully deleted.')
                    return redirect('auth:login')
                except Exception as e:
                    messages.error(request, 'An error occurred while deleting your account. Please try again.')
                    return redirect('dashboard:settings')
        else:
            request.user.first_name = request.POST.get('first_name', '').strip()
            request.user.last_name = request.POST.get('last_name', '').strip()
            request.user.save()

            if profile:
                profile.phone = request.POST.get('phone', '').strip()
                profile.location = request.POST.get('location', '').strip()
                profile.bio = request.POST.get('bio', '').strip()
                profile.website = request.POST.get('website', '').strip()
                profile.save()

            messages.success(request, 'Profile updated successfully.')

        return redirect('dashboard:settings')

    def _get_profile(self, create=False):
        try:
            return UserProfile.objects.get(user=self.request.user)
        except UserProfile.DoesNotExist:
            if create:
                return UserProfile.objects.create(user=self.request.user)
            return None


class AlertsView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/alerts.html'


class WatchlistView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/watchlist.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries, stats = self._build_watchlist_entries()
        context.update(stats)
        context['watchlist_entries'] = entries
        context['error'] = self.request.GET.get('error')
        return context

    def _build_watchlist_entries(self):
        watchlist_items = Watchlist.objects.filter(
            user=self.request.user
        ).select_related('influencer').order_by('-added_at')

        entries = []
        if not watchlist_items:
            return entries, {
                'total_followed': 0,
                'avg_accuracy': 0,
                'active_calls_count': 0,
                'potential_value': 0,
            }

        influencer_ids = [
            item.influencer.influencer_id
            for item in watchlist_items
            if item.influencer_id and item.influencer
        ]

        if not influencer_ids:
            return entries, {
                'total_followed': 0,
                'avg_accuracy': 0,
                'active_calls_count': 0,
                'potential_value': 0,
            }

        active_filter = (
            (Q(done=False) | Q(done__isnull=True)) &
            (Q(target_hit=False) | Q(target_hit__isnull=True)) &
            (Q(stoploss_hit=False) | Q(stoploss_hit__isnull=True))
        )

        stats_map = {
            row['influencer_id']: row
            for row in TradeCall.objects.filter(
                status='True',
                influencer_id__in=influencer_ids
            ).values('influencer_id').annotate(
                total_calls=Count('id'),
                wins=Count('id', filter=Q(target_hit=True)),
                losses=Count('id', filter=Q(stoploss_hit=True)),
                active_calls=Count('id', filter=active_filter),
                last_created_at=Max('created_at'),
            )
        }

        profit_expr = ExpressionWrapper(
            (F('assumed_target') - F('assumed_entry_price')) / F('assumed_entry_price') * 100.0,
            output_field=FloatField()
        )

        returns_map = {
            row['influencer_id']: row['avg_return']
            for row in TradeCall.objects.filter(
                status='True',
                influencer_id__in=influencer_ids,
                target_hit=True,
                assumed_entry_price__isnull=False,
                assumed_entry_price__gt=0,
                assumed_target__isnull=False,
            ).annotate(
                return_pct=profit_expr
            ).values('influencer_id').annotate(
                avg_return=Avg('return_pct')
            )
        }

        accuracy_values = []
        avg_return_values = []
        total_active_calls = 0

        for item in watchlist_items:
            influencer = item.influencer
            if not influencer:
                continue

            stats = stats_map.get(influencer.influencer_id, {})
            total_calls = stats.get('total_calls', 0) or 0
            wins = stats.get('wins', 0) or 0
            losses = stats.get('losses', 0) or 0
            resolved = wins + losses
            accuracy = round((wins / resolved) * 100, 1) if resolved else 0
            if accuracy:
                accuracy_values.append(accuracy)

            active_calls = stats.get('active_calls', 0) or 0
            total_active_calls += active_calls

            avg_return = returns_map.get(influencer.influencer_id)
            if avg_return is not None:
                avg_return = round(avg_return, 1)
                avg_return_values.append(avg_return)

            last_display, last_hours = self._format_last_active(stats.get('last_created_at'))

            entries.append({
                'watchlist_id': item.id,
                'influencer_id': influencer.influencer_id,
                'channel_name': influencer.channel_name or influencer.author_name or 'Unknown',
                'author_name': influencer.author_name,
                'platform': influencer.platform or 'Unknown',
                'avatar': self._build_avatar(influencer),
                'accuracy': accuracy,
                'total_calls': total_calls,
                'active_calls': active_calls,
                'avg_return': avg_return,
                'last_active_display': last_display,
                'last_active_hours': last_hours if last_hours is not None else '',
                'asset_symbol': None,
            })

        stats_summary = {
            'total_followed': len(entries),
            'avg_accuracy': round(sum(accuracy_values) / len(accuracy_values), 1) if accuracy_values else 0,
            'active_calls_count': total_active_calls,
            'potential_value': round(sum(avg_return_values) / len(avg_return_values), 1) if avg_return_values else 0,
        }

        return entries, stats_summary

    def _format_last_active(self, created_at):
        if not created_at:
            return ('No recent activity', None)
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at)
        delta = timezone.now() - created_at
        seconds = delta.total_seconds()
        if seconds < 60:
            return ('Just now', seconds / 3600)
        if seconds < 3600:
            minutes = int(seconds / 60)
            return (f"{minutes}m ago", minutes / 60)
        if seconds < 86400:
            hours = int(seconds / 3600)
            return (f"{hours}h ago", hours)
        days = int(seconds / 86400)
        return (f"{days}d ago", days * 24)

    def _build_avatar(self, influencer):
        name = influencer.channel_name or influencer.author_name or '?'
        name = name.strip()
        if not name:
            return '?'
        parts = name.split()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

class SubmitInfluencerView(LoginRequiredMixin, TemplateView):
    """
    Submit influencer for review with auto-approval logic
    """
    template_name = 'dashboard/submit_influencer.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get submission statistics for the current user
        try:
            from .models import InfluencerSubmission
            
            user_submissions = InfluencerSubmission.objects.filter(submitted_by=self.request.user)
            context['user_submissions'] = user_submissions.count()
            context['approved_submissions'] = user_submissions.filter(status='approved').count()
            context['pending_submissions'] = user_submissions.filter(status='pending').count()
            
            # Calculate auto-approval rate
            approved_count = context['approved_submissions']
            total_count = context['user_submissions']
            context['auto_approval_rate'] = round((approved_count / total_count) * 100) if total_count > 0 else 0
            
            # Get recent submissions
            context['recent_submissions'] = user_submissions.order_by('-created_at')[:5]
        except ImportError:
            # Handle case where model doesn't exist yet
            context['user_submissions'] = 0
            context['approved_submissions'] = 0
            context['pending_submissions'] = 0
            context['auto_approval_rate'] = 0
            context['recent_submissions'] = []
        
        return context
    
    def post(self, request, *args, **kwargs):
        """
        Handle TikTok/Twitter/YouTube submission with Apify verification
        """
        from django.http import JsonResponse
        
        try:
            platform = (request.POST.get('platform') or '').strip().lower()
            url = (request.POST.get('url') or '').strip()
            channel_name = (request.POST.get('channel_name') or '').strip()
            categories = request.POST.getlist('categories')  # Get multiple categories
            author_name = (request.POST.get('author_name') or '').strip()
            description = request.POST.get('description', '').strip()
            
            logger.info(f'Submission received - Platform: {platform}, Channel: {channel_name}, Categories: {categories}, User: {request.user.username}')
            
            # Validation
            if not platform or not url or not channel_name or not categories:
                return JsonResponse({
                    'success': False,
                    'message': 'Platform, channel name, categories, and profile URL are required.'
                })
            
            allowed_platforms = ['tiktok', 'twitter', 'youtube', 'telegram']
            if platform not in allowed_platforms:
                return JsonResponse({
                    'success': False,
                    'message': 'Only TikTok, Twitter, YouTube, and Telegram submissions are accepted.'
                })
            
            # Use Apify service to verify platform profile
            try:
                verification_result = apify_service.verify_profile(platform, url)
                
                if not verification_result.get('success'):
                    # Log the verification failure but continue with mock data
                    verification_error = verification_result.get('error', 'Verification failed')
                    logger.warning(f'Apify verification failed for {platform} {url}: {verification_error}')
                    # Use mock data as fallback - set to 0 followers to trigger manual review
                    verification_result = {
                        'success': True,
                        'username': channel_name,
                        'display_name': channel_name,
                        'bio': '',
                        'followers': 0,  # Set to 0 to trigger manual review when verification fails
                        'following': 0,
                        'posts_count': 0,
                        'verified': False,
                        'avatar_url': '',
                        'meets_criteria': False,
                        'mock_data': True,
                        'verification_error': verification_error
                    }
            except Exception as e:
                logger.error(f'Apify service error for {platform} {url}: {str(e)}')
                # Use mock data as fallback - set to 0 followers to trigger manual review
                verification_result = {
                    'success': True,
                    'username': channel_name,
                    'display_name': channel_name,
                    'bio': '',
                    'followers': 0,  # Set to 0 to trigger manual review when verification fails
                    'following': 0,
                    'posts_count': 0,
                    'verified': False,
                    'avatar_url': '',
                    'meets_criteria': False,
                    'mock_data': True,
                    'verification_error': f'Service error: {str(e)}'
                }
            
            detected_followers = verification_result.get('followers', 0)
            
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '')
            if ip_address:
                ip_address = ip_address.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            # Use first category for backward compatibility
            primary_category = categories[0] if categories else ''
            
            submission_payload = {
                'platform': platform,
                'url': url,
                'channel_name': channel_name,
                'category': primary_category,  # Primary category
                'categories': categories,  # All selected categories
                'author_name': author_name,
                'description': description,
                'username': verification_result.get('username', ''),
                'display_name': verification_result.get('display_name', channel_name),
                'bio': verification_result.get('bio', ''),
                'followers': detected_followers,
                'following': verification_result.get('following', 0),
                'posts_count': verification_result.get('posts_count', 0),
                'verified': verification_result.get('verified', False),
                'avatar_url': verification_result.get('avatar_url', ''),
                'meets_criteria': verification_result.get('meets_criteria', False),
                'mock_data': verification_result.get('mock_data', False),
                'verification_error': verification_result.get('verification_error', ''),
                'submitted_by': request.user,
                'ip_address': ip_address,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }
            
            logger.info(f'Calling auto-approval service for {channel_name}')
            approval_result = enhanced_auto_approval_service.process_submission(submission_payload)
            
            logger.info(f'Auto-approval result for {channel_name}: {approval_result}')
            
            if not approval_result.get('success'):
                logger.error(f'Auto-approval failed for {channel_name}: {approval_result.get("error")}')
                return JsonResponse({
                    'success': False,
                    'message': approval_result.get('error', 'Failed to record submission.')
                })
            
            response_data = {
                'success': True,
                'auto_approved': approval_result.get('auto_approved', False),
                'submission_id': approval_result.get('submission_id'),
                'approval_score': approval_result.get('approval_score', 0),
                'verification_data': verification_result,
                'status': approval_result.get('status', 'pending'),
                'reason': approval_result.get('reason', ''),
                'message': approval_result.get('message', 'Submission processed successfully!')
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'An error occurred: {str(e)}'
            })
    


class SubmissionsTrackingView(LoginRequiredMixin, TemplateView):
    """
    Track submissions and their status
    """
    template_name = 'dashboard/submissions_tracking.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            from .models import InfluencerSubmission
            
            # Get user's submissions with filtering
            status_filter = self.request.GET.get('status', 'all')
            platform_filter = self.request.GET.get('platform', 'all')
            
            submissions = InfluencerSubmission.objects.filter(submitted_by=self.request.user)
            
            if status_filter != 'all':
                submissions = submissions.filter(status=status_filter)
            if platform_filter != 'all':
                submissions = submissions.filter(platform=platform_filter)
            
            context['submissions'] = submissions.order_by('-created_at')
            context['selected_status'] = status_filter
            context['selected_platform'] = platform_filter
            
            # Statistics
            all_user_submissions = InfluencerSubmission.objects.filter(submitted_by=self.request.user)
            context['total_submissions'] = all_user_submissions.count()
            context['approved_count'] = all_user_submissions.filter(status='approved').count()
            context['pending_count'] = all_user_submissions.filter(status='pending').count()
            context['rejected_count'] = all_user_submissions.filter(status='rejected').count()
            
        except ImportError:
            context['submissions'] = []
            context['total_submissions'] = 0
            context['approved_count'] = 0
            context['pending_count'] = 0
            context['rejected_count'] = 0
            context['selected_status'] = 'all'
            context['selected_platform'] = 'all'
        
        return context


class AdminManagementView(LoginRequiredMixin, TemplateView):
    """
    Admin management dashboard for reviewing submissions
    """
    template_name = 'dashboard/admin_management.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Only allow staff users
        if not request.user.is_staff:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("You don't have permission to access this page.")
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            from .models import InfluencerSubmission
            
            # Get filter parameters
            status_filter = self.request.GET.get('status', 'pending')
            platform_filter = self.request.GET.get('platform', 'all')
            
            # Base query
            submissions = InfluencerSubmission.objects.select_related('submitted_by')
            
            if status_filter != 'all':
                submissions = submissions.filter(status=status_filter)
            if platform_filter != 'all':
                submissions = submissions.filter(platform=platform_filter)
            
            context['submissions'] = submissions.order_by('-created_at')
            context['selected_status'] = status_filter
            context['selected_platform'] = platform_filter
            
            # Admin statistics
            all_submissions = InfluencerSubmission.objects.all()
            context['total_submissions'] = all_submissions.count()
            context['pending_review'] = all_submissions.filter(status='pending').count()
            context['approved_submissions'] = all_submissions.filter(status='approved').count()
            context['rejected_submissions'] = all_submissions.filter(status='rejected').count()
            context['auto_approved_count'] = all_submissions.filter(auto_approved=True).count()
            
            # Platform distribution
            from django.db.models import Count
            context['platform_stats'] = all_submissions.values('platform').annotate(
                count=Count('platform')
            ).order_by('-count')
            
        except ImportError:
            context['submissions'] = []
            context['total_submissions'] = 0
            context['pending_review'] = 0
            context['approved_submissions'] = 0
            context['rejected_submissions'] = 0
            context['auto_approved_count'] = 0
            context['platform_stats'] = []
            context['selected_status'] = 'pending'
            context['selected_platform'] = 'all'
        
        return context
    
    def post(self, request, *args, **kwargs):
        """
        Handle admin actions on submissions
        """
        from django.http import JsonResponse
        from django.contrib import messages
        
        try:
            action = request.POST.get('action')
            submission_id = request.POST.get('submission_id')
            
            if not action or not submission_id:
                return JsonResponse({'success': False, 'message': 'Invalid parameters'})
            
            from .models import InfluencerSubmission
            submission = InfluencerSubmission.objects.get(id=submission_id)
            
            if action == 'approve':
                submission.status = 'approved'
                submission.reviewed_by = request.user
                submission.reviewed_at = timezone.now()
                submission.save()
                
                # Add to main influencer database
                self._add_to_influencer_database(submission)
                
                messages.success(request, f'Submission for {submission.channel_name} approved successfully!')
                
            elif action == 'reject':
                rejection_reason = request.POST.get('reason', 'No reason provided')
                submission.status = 'rejected'
                submission.reviewed_by = request.user
                submission.reviewed_at = timezone.now()
                submission.rejection_reason = rejection_reason
                submission.save()
                
                messages.success(request, f'Submission for {submission.channel_name} rejected.')
                
            elif action == 'bulk_approve':
                submission_ids = request.POST.getlist('submission_ids[]')
                updated_count = InfluencerSubmission.objects.filter(
                    id__in=submission_ids,
                    status='pending'
                ).update(
                    status='approved',
                    reviewed_by=request.user,
                    reviewed_at=timezone.now()
                )
                
                messages.success(request, f'{updated_count} submissions approved successfully!')
                
            return JsonResponse({'success': True})
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    def _add_to_influencer_database(self, submission):
        """Add approved submission to main influencer database"""
        from influencers.models import Influencer

        try:
            existing = Influencer.objects.filter(url=submission.url).first()
            if not existing:
                from django.utils import timezone
                influencer = Influencer.objects.create(
                    channel_name=submission.channel_name,
                    author_name=submission.author_name or '',
                    url=submission.url,
                    platform=submission.platform,
                    follower_count=submission.follower_count or 0,
                    created_at=timezone.now()
                )
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Created influencer record {influencer.influencer_id} for {submission.channel_name}")
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Influencer already exists: {existing.influencer_id} for URL {submission.url}")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error adding submission {submission.id} to influencer database: {e}")


class InfluencerProfileView(TemplateView):
    """
    Influencer profile detail view - accessible to all users
    """
    template_name = 'dashboard/influencer_profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        influencer_id = self.kwargs.get('influencer_id')

        try:
            from django.db.models import Count, Avg, Max, Min
            from datetime import timedelta

            # Get the influencer
            influencer = Influencer.objects.get(influencer_id=influencer_id)

            # Get all trade calls for this influencer (only valid tracked calls)
            trade_calls = TradeCall.objects.filter(
                influencer=influencer,
                status='True'
            ).select_related('asset').order_by('-timestamp')

            # Calculate statistics
            total_calls = trade_calls.count()
            successful_calls = trade_calls.filter(target_hit=True).count()
            failed_calls = trade_calls.filter(stoploss_hit=True).count()
            resolved_calls = successful_calls + failed_calls
            accuracy = round((successful_calls / resolved_calls * 100), 1) if resolved_calls > 0 else 0

            # Recent performance (last 7 days)
            last_week = timezone.now() - timedelta(days=7)
            recent_calls = trade_calls.filter(created_at__gte=last_week)
            recent_wins = recent_calls.filter(target_hit=True).count()
            recent_losses = recent_calls.filter(stoploss_hit=True).count()

            # Calculate average return percentage
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

            # Get top assets
            top_assets = trade_calls.values('asset__symbol', 'asset__name').annotate(
                count=Count('id')
            ).order_by('-count')[:5]

            # Recent signals (last 10)
            recent_signals = trade_calls[:10]

            # Format time ago for recent signals
            now = timezone.now()
            signals_data = []
            for call in recent_signals:
                time_ago_str = 'Just now'
                if call.created_at:
                    created_at = call.created_at
                    if timezone.is_naive(created_at):
                        created_at = timezone.make_aware(created_at)
                    time_diff = now - created_at
                    if time_diff.total_seconds() < 60:
                        time_ago_str = f"{int(time_diff.total_seconds())}s ago"
                    elif time_diff.total_seconds() < 3600:
                        time_ago_str = f"{int(time_diff.total_seconds() / 60)}m ago"
                    elif time_diff.total_seconds() < 86400:
                        time_ago_str = f"{int(time_diff.total_seconds() / 3600)}h ago"
                    else:
                        time_ago_str = f"{int(time_diff.total_seconds() / 86400)}d ago"

                # Determine status
                if call.target_hit:
                    status = 'Hit'
                    badge_class = 'success'
                elif call.stoploss_hit:
                    status = 'Stopped'
                    badge_class = 'danger'
                elif call.done:
                    status = 'Closed'
                    badge_class = 'secondary'
                else:
                    status = 'Active'
                    badge_class = 'warning'

                signals_data.append({
                    'call': call,
                    'time_ago': time_ago_str,
                    'status': status,
                    'badge_class': badge_class
                })

            context['influencer'] = influencer
            context['total_calls'] = total_calls
            context['successful_calls'] = successful_calls
            context['failed_calls'] = failed_calls
            context['active_calls'] = max(total_calls - resolved_calls, 0)
            context['accuracy'] = accuracy
            context['recent_wins'] = recent_wins
            context['recent_losses'] = recent_losses
            context['avg_return'] = avg_return
            context['top_assets'] = top_assets
            context['recent_signals'] = signals_data

        except Influencer.DoesNotExist:
            context['influencer'] = None
            context['error'] = 'Influencer not found'

        return context


class SignalDetailView(TemplateView):
    """
    Signal detail view - accessible to all users
    """
    template_name = 'dashboard/signal_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        signal_id = self.kwargs.get('signal_id')

        try:
            # Get the trade call
            signal = TradeCall.objects.select_related('influencer', 'asset').get(id=signal_id)

            # Calculate time ago
            now = timezone.now()
            time_ago_str = 'Just now'
            if signal.created_at:
                created_at = signal.created_at
                if timezone.is_naive(created_at):
                    created_at = timezone.make_aware(created_at)
                time_diff = now - created_at
                if time_diff.total_seconds() < 60:
                    time_ago_str = f"{int(time_diff.total_seconds())}s ago"
                elif time_diff.total_seconds() < 3600:
                    time_ago_str = f"{int(time_diff.total_seconds() / 60)}m ago"
                elif time_diff.total_seconds() < 86400:
                    time_ago_str = f"{int(time_diff.total_seconds() / 3600)}h ago"
                else:
                    time_ago_str = f"{int(time_diff.total_seconds() / 86400)}d ago"

            # Determine status
            if signal.target_hit:
                status = 'Hit'
                badge_class = 'success'
            elif signal.stoploss_hit:
                status = 'Stopped'
                badge_class = 'danger'
            elif signal.done:
                status = 'Closed'
                badge_class = 'secondary'
            else:
                status = 'Active'
                badge_class = 'warning'

            context['signal'] = signal
            context['time_ago'] = time_ago_str
            context['status'] = status
            context['badge_class'] = badge_class
            # Determine best full-length content
            content_candidates = [
                getattr(signal, field) for field in [
                    'signal', 'text', 'description', 'target'
                ]
                if getattr(signal, field)
            ]
            if content_candidates:
                context['signal_content'] = max(content_candidates, key=lambda value: len(str(value)))
            else:
                context['signal_content'] = None

        except TradeCall.DoesNotExist:
            context['signal'] = None
            context['error'] = 'Signal not found'

        return context

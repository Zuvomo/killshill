from math import ceil
from typing import Dict, Any

from django.db.models import Q, Count

from influencers.models import Influencer, TradeCall
from dashboard.constants import (
    SUPPORTED_CATEGORY_VALUES,
    SUPPORTED_PLATFORM_VALUES,
)
from dashboard.utils.statistics import clopper_pearson_interval


def _infer_category(influencer: Influencer) -> str:
    trade_calls = TradeCall.objects.filter(
        status='True',
        influencer=influencer
    ).select_related('asset').exclude(asset__isnull=True)[:20]

    category_counts = {'crypto': 0, 'stocks': 0, 'forex': 0, 'commodities': 0}
    for call in trade_calls:
        asset_type = call.asset.asset_type.lower() if call.asset and call.asset.asset_type else ''
        if 'stock' in asset_type or 'equity' in asset_type:
            category_counts['stocks'] += 1
        elif 'forex' in asset_type or 'currency' in asset_type or 'fx' in asset_type:
            category_counts['forex'] += 1
        elif 'commodit' in asset_type or 'gold' in asset_type or 'oil' in asset_type:
            category_counts['commodities'] += 1
        else:
            category_counts['crypto'] += 1

    max_category = max(category_counts, key=category_counts.get)
    if category_counts[max_category] == 0:
        return 'Crypto'
    return max_category.capitalize()


def perform_influencer_search(
    query: str = '',
    platform: str = '',
    category: str = '',
    sort_by: str = 'relevance',
    page: int = 1,
    page_size: int = 12,
) -> Dict[str, Any]:
    query = (query or '').strip()
    platform = (platform or '').strip()
    category = (category or '').strip().lower()
    sort_by = sort_by if sort_by in {'relevance', 'accuracy', 'calls', 'name'} else 'relevance'

    if platform not in SUPPORTED_PLATFORM_VALUES:
        platform = ''
    if category not in SUPPORTED_CATEGORY_VALUES:
        category = ''

    page = max(1, int(page or 1))
    page_size = max(6, min(30, int(page_size or 12)))

    influencer_queryset = Influencer.objects.all()

    if query:
        search_query = (
            Q(channel_name__icontains=query) |
            Q(author_name__icontains=query) |
            Q(url__icontains=query)
        )
        influencer_queryset = influencer_queryset.filter(search_query)

    if platform:
        influencer_queryset = influencer_queryset.filter(platform__icontains=platform)

    influencer_queryset = influencer_queryset.annotate(
        total_calls=Count('tradecall', filter=Q(tradecall__status='True')),
        successful_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__target_hit=True)),
        failed_calls=Count('tradecall', filter=Q(tradecall__status='True', tradecall__stoploss_hit=True))
    ).filter(total_calls__gt=0)

    max_candidates = 300
    candidates = list(influencer_queryset[:max_candidates])

    results = []
    for influencer in candidates:
        total_calls = influencer.total_calls or 0
        successful_calls = influencer.successful_calls or 0
        failed_calls = influencer.failed_calls or 0
        resolved_calls = successful_calls + failed_calls
        accuracy = round((successful_calls / resolved_calls) * 100, 1) if resolved_calls > 0 else 0

        inferred_category = _infer_category(influencer)
        if category and inferred_category.lower() != category:
            continue

        ci_low, ci_high = clopper_pearson_interval(successful_calls, resolved_calls) if resolved_calls > 0 else (0.0, 0.0)
        results.append({
            'id': influencer.influencer_id,
            'channel_name': influencer.channel_name or influencer.author_name or 'Unknown',
            'author_name': influencer.author_name,
            'platform': influencer.platform or 'Unknown',
            'url': influencer.url,
            'total_calls': total_calls,
            'successful_calls': successful_calls,
            'failed_calls': failed_calls,
            'resolved_calls': resolved_calls,
            'accuracy': accuracy,
            'category': inferred_category,
            'confidence_value': ci_low,
            'confidence_ci': {'low': ci_low, 'high': ci_high},
        })

    if sort_by == 'accuracy':
        results.sort(key=lambda x: (x['accuracy'], x['total_calls']), reverse=True)
    elif sort_by == 'calls':
        results.sort(key=lambda x: x['total_calls'], reverse=True)
    elif sort_by == 'name':
        results.sort(key=lambda x: x['channel_name'].lower())
    else:
        if query:
            results.sort(key=lambda x: (x['accuracy'], x['total_calls']), reverse=True)
        else:
            results.sort(key=lambda x: (x['total_calls'], x['accuracy']), reverse=True)

    total = len(results)
    total_pages = ceil(total / page_size) if total else 0
    page = min(page, total_pages) if total_pages else 1
    start = (page - 1) * page_size if total_pages else 0
    end = start + page_size if total_pages else 0
    page_results = results[start:end] if total else []

    return {
        'results': page_results,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_previous': page > 1,
        'query': query,
    }

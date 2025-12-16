from django.urls import path
from . import views, api_views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard views
    path('', views.DashboardHomeView.as_view(), name='home'),
    path('leaderboard/', views.LeaderboardView.as_view(), name='leaderboard'),
    path('trending-kols/', views.TrendingKOLsView.as_view(), name='trending_kols'),
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),
    path('insights/', views.InsightsDashboardView.as_view(), name='insights'),
    path('signals/', views.SignalsView.as_view(), name='signals'),
    path('search/', views.SearchView.as_view(), name='search'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    path('alerts/', views.AlertsView.as_view(), name='alerts'),
    path('watchlist/', views.WatchlistView.as_view(), name='watchlist'),
    
    # Submission Management
    path('submit-influencer/', views.SubmitInfluencerView.as_view(), name='submit_influencer'),
    path('submissions-tracking/', views.SubmissionsTrackingView.as_view(), name='submissions_tracking'),
    path('admin-management/', views.AdminManagementView.as_view(), name='admin_management'),

    # Signal Details
    path('signal/<int:signal_id>/', views.SignalDetailView.as_view(), name='signal_detail'),

    # Influencer Profile
    path('influencer/<int:influencer_id>/', views.InfluencerProfileView.as_view(), name='influencer_profile'),

    # API endpoints for real-time data
    path('api/stats/', api_views.dashboard_stats_api, name='api_stats'),
    path('api/timeline/', api_views.submission_timeline_api, name='api_timeline'),
    path('api/platforms/', api_views.platform_distribution_api, name='api_platforms'),
    path('api/activity/', api_views.recent_activity_api, name='api_activity'),
    path('api/performers/', api_views.top_performers_api, name='api_performers'),
    path('api/trade-calls/', api_views.trade_calls_api, name='api_trade_calls'),
    path('api/notifications/', api_views.user_notifications_api, name='api_notifications'),
    path('api/notifications/mark-read/', api_views.mark_notification_read_api, name='api_mark_notification_read'),
    path('api/notifications/mark-all-read/', api_views.mark_all_notifications_read_api, name='api_mark_all_notifications_read'),
    path('api/refresh/', api_views.refresh_dashboard_data, name='api_refresh'),
    path('api/search/', api_views.search_influencers_api, name='api_search'),
]

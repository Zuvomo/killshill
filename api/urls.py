from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Leaderboard and Rankings
    path('leaderboard/', views.leaderboard_api, name='leaderboard'),
    path('trending-kols/', views.trending_kols_api, name='trending_kols'),
    path('top-signals/', views.top_signals_api, name='top_signals'),
    
    # Influencer Management
    path('submit-influencer/', views.submit_influencer_api, name='submit_influencer'),
    path('search/', views.search_influencers_api, name='search_influencers'),
    path('influencer/<int:influencer_id>/mini-profile/', views.influencer_mini_profile_api, name='influencer_mini_profile'),
    
    # Dashboard APIs
    path('v1/dashboard/stats/', views.dashboard_stats_api, name='dashboard_stats'),
    path('v1/submissions/recent/', views.recent_submissions_api, name='recent_submissions'),
    path('v1/submissions/<int:submission_id>/process/', views.process_submission_api, name='process_submission'),
    path('v1/submissions/process-auto-approvals/', views.process_auto_approvals_api, name='process_auto_approvals'),
    
    # Analytics
    path('analytics/', views.analytics_data_api, name='analytics_data'),

    # Abuse Reporting
    path('report/', views.report_abuse_api, name='report_abuse'),

    # Watchlist
    path('watchlist/', views.watchlist_api, name='watchlist'),
    path('watchlist/<int:watchlist_id>/', views.watchlist_remove_api, name='watchlist_remove'),

    # Simulation Engine
    path('simulate/', views.simulate_returns_api, name='simulate_returns'),
]
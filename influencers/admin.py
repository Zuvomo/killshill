from django.contrib import admin
from django.utils.html import format_html
from .models import Influencer, Asset, TradeCall

def format_price_admin(price):
    """
    Format price with dynamic decimal places for admin interface
    """
    if not price:
        return "-"
    
    try:
        price = float(price)
    except (ValueError, TypeError):
        return "-"
    
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.01:
        return f"${price:.6f}"
    elif price >= 0.0001:
        return f"${price:.8f}"
    else:
        if price == 0:
            return "$0.00"
        return f"${price:.10f}".rstrip('0').rstrip('.')

def format_volume_admin(volume):
    """
    Format volume with abbreviations for admin
    """
    if not volume:
        return "-"
    
    try:
        volume = float(volume)
    except (ValueError, TypeError):
        return "-"
    
    if volume >= 1_000_000_000:
        return f"${volume/1_000_000_000:.2f}B"
    elif volume >= 1_000_000:
        return f"${volume/1_000_000:.2f}M"
    elif volume >= 1_000:
        return f"${volume/1_000:.2f}K"
    else:
        return f"${volume:.2f}"


@admin.register(Influencer)
class InfluencerAdmin(admin.ModelAdmin):
    list_display = [
        'influencer_id', 'channel_name', 'author_name', 'platform', 
        'formatted_follower_count', 'platform_link', 'trade_calls_count', 'created_at'
    ]
    list_filter = ['platform', 'created_at']
    search_fields = ['channel_name', 'author_name', 'url']
    readonly_fields = ['influencer_id', 'created_at']
    ordering = ['-influencer_id']
    list_per_page = 25
    list_max_show_all = 100
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('influencer_id', 'channel_name', 'author_name', 'follower_count')
        }),
        ('Platform Details', {
            'fields': ('platform', 'url'),
            'description': 'Platform information and profile URL'
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def platform_link(self, obj):
        if obj.url:
            return format_html('<a href="{}" target="_blank">View Profile</a>', obj.url)
        return "-"
    platform_link.short_description = "Profile Link"
    
    def formatted_follower_count(self, obj):
        if obj.follower_count:
            if obj.follower_count >= 1_000_000:
                return f"{obj.follower_count/1_000_000:.1f}M"
            elif obj.follower_count >= 1_000:
                return f"{obj.follower_count/1_000:.1f}K"
            else:
                return f"{obj.follower_count:,}"
        return "0"
    formatted_follower_count.short_description = "Followers"
    formatted_follower_count.admin_order_field = "follower_count"
    
    def trade_calls_count(self, obj):
        return obj.tradecall_set.count()
    trade_calls_count.short_description = "Trade Calls"


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'symbol', 'name', 'asset_type', 'exchange', 
        'formatted_price', 'formatted_market_cap', 'formatted_volume', 'change24hr_display'
    ]
    list_filter = ['asset_type', 'exchange']
    search_fields = ['symbol', 'name']
    ordering = ['-market_cap']
    list_per_page = 25
    list_max_show_all = 100
    
    fieldsets = (
        ('Asset Information', {
            'fields': ('symbol', 'name', 'asset_type', 'exchange')
        }),
        ('Market Data', {
            'fields': ('current_price', 'market_cap', 'volume', 'change24hr'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def formatted_price(self, obj):
        return format_price_admin(obj.current_price)
    formatted_price.short_description = "Current Price"
    formatted_price.admin_order_field = "current_price"
    
    def formatted_market_cap(self, obj):
        return format_volume_admin(obj.market_cap)
    formatted_market_cap.short_description = "Market Cap"
    formatted_market_cap.admin_order_field = "market_cap"
    
    def formatted_volume(self, obj):
        return format_volume_admin(obj.volume)
    formatted_volume.short_description = "Volume (24h)"
    formatted_volume.admin_order_field = "volume"
    
    def change24hr_display(self, obj):
        if obj.change24hr is not None:
            color = "green" if obj.change24hr >= 0 else "red"
            formatted_change = f"{obj.change24hr:+.2f}%"
            return format_html(
                '<span style="color: {}">{}</span>',
                color, formatted_change
            )
        return "-"
    change24hr_display.short_description = "24h Change"
    change24hr_display.admin_order_field = "change24hr"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()


@admin.register(TradeCall)
class TradeCallAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'uuid_short', 'influencer_name', 'asset_symbol', 'signal_display', 
        'formatted_entry_price', 'status_display', 'created_at'
    ]
    list_filter = ['status', 'signal', 'created_at', 'asset__asset_type']
    search_fields = ['uuid', 'influencer__channel_name', 'asset__symbol', 'text']
    readonly_fields = ['id', 'uuid', 'created_at']
    raw_id_fields = ['influencer', 'asset']
    ordering = ['-created_at']
    list_per_page = 25
    list_max_show_all = 100
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'uuid', 'influencer', 'asset', 'status')
        }),
        ('Trade Details', {
            'fields': (
                'signal', 'entry_price', 'assumed_entry_price', 'stoploss_price',
                'target', 'target_first', 'target_second', 'target_third', 'target_fourth',
                'assumed_target', 'timeframe'
            )
        }),
        ('Content', {
            'fields': ('text', 'description')
        }),
        ('Performance', {
            'fields': ('stoploss_percentage', 'target_percentage')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_workflow_started_at'),
            'classes': ('collapse',)
        }),
    )
    
    def influencer_name(self, obj):
        return obj.influencer.channel_name if obj.influencer else "Unknown"
    influencer_name.short_description = "Influencer"
    
    def asset_symbol(self, obj):
        return obj.asset.symbol
    asset_symbol.short_description = "Asset"
    
    def uuid_short(self, obj):
        return obj.uuid[:8] + "..." if obj.uuid else "-"
    uuid_short.short_description = "UUID"
    
    def signal_display(self, obj):
        if obj.signal:
            color_map = {
                'BUY': 'green',
                'SELL': 'red',
                'HOLD': 'orange'
            }
            color = color_map.get(obj.signal.upper(), 'blue')
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>', 
                color, obj.signal
            )
        return "-"
    signal_display.short_description = "Signal"
    
    def formatted_entry_price(self, obj):
        if obj.assumed_entry_price:
            return format_price_admin(obj.assumed_entry_price)
        elif obj.entry_price:
            return str(obj.entry_price)
        return "-"
    formatted_entry_price.short_description = "Entry Price"
    
    def status_display(self, obj):
        if obj.status:
            status_colors = {
                'ACTIVE': '#28a745',
                'COMPLETED': '#007bff', 
                'FAILED': '#dc3545',
                'PENDING': '#ffc107'
            }
            color = status_colors.get(obj.status.upper(), '#6c757d')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
                color, obj.status
            )
        return "-"
    status_display.short_description = "Status"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('influencer', 'asset')


# Customize admin site header and title
admin.site.site_header = "Killshill Admin"
admin.site.site_title = "Killshill Admin Portal"
admin.site.index_title = "Welcome to Killshill Administration"

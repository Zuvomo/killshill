from rest_framework import serializers
from influencers.models import Influencer, Asset, TradeCall


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = [
            'id', 'symbol', 'name', 'exchange', 'asset_type',
            'market_cap', 'volume', 'change24hr', 'current_price', 'created_at'
        ]


class InfluencerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Influencer
        fields = [
            'influencer_id', 'channel_name', 'url', 'platform', 'author_name'
        ]


class TradeCallSerializer(serializers.ModelSerializer):
    influencer = InfluencerSerializer(read_only=True)
    asset = AssetSerializer(read_only=True)
    
    class Meta:
        model = TradeCall
        fields = [
            'id', 'uuid', 'timestamp', 'signal', 'entry_price', 'assumed_entry_price',
            'stoploss_price', 'target', 'target_first', 'target_second', 'target_third',
            'target_fourth', 'timeframe', 'text', 'stoploss_percentage', 'status',
            'description', 'target_percentage', 'assumed_target', 'asset', 'influencer',
            'created_at', 'last_workflow_started_at'
        ]


class InfluencerSubmissionSerializer(serializers.Serializer):
    """
    Serializer for submitting new influencers for approval
    """
    username = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=150, required=False)
    platform = serializers.ChoiceField(choices=[
        ('twitter', 'Twitter/X'),
        ('telegram', 'Telegram'),
        ('youtube', 'YouTube'),
        ('discord', 'Discord'),
        ('web', 'Website')
    ])
    platform_url = serializers.URLField()
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    follower_count = serializers.IntegerField(min_value=0, required=False, default=0)
    
    def validate_platform_url(self, value):
        """
        Validate platform URL matches the selected platform
        """
        platform = self.initial_data.get('platform')
        
        if platform == 'twitter' and 'twitter.com' not in value and 'x.com' not in value:
            raise serializers.ValidationError("Please provide a valid Twitter/X URL")
        elif platform == 'telegram' and 'telegram.me' not in value and 't.me' not in value:
            raise serializers.ValidationError("Please provide a valid Telegram URL")
        elif platform == 'youtube' and 'youtube.com' not in value:
            raise serializers.ValidationError("Please provide a valid YouTube URL")
        elif platform == 'discord' and 'discord' not in value:
            raise serializers.ValidationError("Please provide a valid Discord URL")
        
        return value


class LeaderboardFilterSerializer(serializers.Serializer):
    """
    Serializer for leaderboard filtering parameters
    """
    category = serializers.ChoiceField(
        choices=[('all', 'All'), ('crypto', 'Crypto'), ('stocks', 'Stocks'), ('forex', 'Forex')],
        default='all'
    )
    platform = serializers.ChoiceField(
        choices=[('all', 'All'), ('twitter', 'Twitter'), ('telegram', 'Telegram'), ('youtube', 'YouTube')],
        default='all'
    )
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)


class SearchSerializer(serializers.Serializer):
    """
    Serializer for search parameters
    """
    q = serializers.CharField(max_length=200, required=True)
    platform = serializers.ChoiceField(
        choices=[('all', 'All'), ('twitter', 'Twitter'), ('telegram', 'Telegram'), ('youtube', 'YouTube')],
        default='all'
    )
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)
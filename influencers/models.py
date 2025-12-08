from django.db import models


class Influencer(models.Model):
    PLATFORM_CHOICES = [
        ('tiktok', 'TikTok'),
        ('twitter', 'Twitter'),
        ('youtube', 'YouTube'),
        ('telegram', 'Telegram'),
    ]
    
    influencer_id = models.BigAutoField(primary_key=True, db_column='influencer_id')
    channel_name = models.TextField(null=True, blank=True)
    url = models.CharField(max_length=500, null=True, blank=True)
    platform = models.CharField(max_length=255, choices=PLATFORM_CHOICES, null=True, blank=True)
    author_name = models.CharField(max_length=255, null=True, blank=True)
    follower_count = models.PositiveIntegerField(default=0, help_text="Number of followers/subscribers")
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'influencer'
        managed = False  # Don't let Django manage this table

    def __str__(self):
        return self.channel_name or f"Influencer {self.influencer_id}"


class Asset(models.Model):
    id = models.BigIntegerField(unique=True)
    created_at = models.DateTimeField(null=True, blank=True)
    symbol = models.CharField(max_length=255, primary_key=True)  # symbol is the actual PK in Supabase
    exchange = models.CharField(max_length=255, null=True, blank=True)
    asset_type = models.CharField(max_length=255, null=True, blank=True)
    market_cap = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    change24hr = models.FloatField(null=True, blank=True)
    current_price = models.FloatField(null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'asset'
        managed = False  # Don't let Django manage this table

    def __str__(self):
        return f"{self.symbol} - {self.name}"


class TradeCall(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.CharField(max_length=255, unique=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    signal = models.TextField(null=True, blank=True)
    entry_price = models.CharField(max_length=500, null=True, blank=True)
    assumed_entry_price = models.FloatField(null=True, blank=True)
    stoploss_price = models.FloatField(null=True, blank=True)
    target = models.CharField(max_length=500, null=True, blank=True)
    target_first = models.FloatField(null=True, blank=True)
    target_second = models.FloatField(null=True, blank=True)
    target_third = models.FloatField(null=True, blank=True)
    target_fourth = models.FloatField(null=True, blank=True)
    timeframe = models.DateTimeField(null=True, blank=True)
    text = models.CharField(max_length=500, null=True, blank=True)
    stoploss_percentage = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    description = models.CharField(max_length=500, null=True, blank=True)
    target_percentage = models.CharField(max_length=255, null=True, blank=True)
    assumed_target = models.FloatField(null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.DO_NOTHING, to_field='id')  # References id field, not PK
    influencer = models.ForeignKey(Influencer, on_delete=models.DO_NOTHING, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    last_workflow_started_at = models.DateTimeField(null=True, blank=True)
    stoploss_hit = models.BooleanField(null=True, blank=True)
    credibility = models.CharField(max_length=255, null=True, blank=True)
    done = models.BooleanField(null=True, blank=True)
    target_hit = models.BooleanField(null=True, blank=True)
    target_achieved = models.SmallIntegerField(null=True, blank=True)
    web_influencer_details = models.ForeignKey('WebInfluencerDetails', on_delete=models.DO_NOTHING, null=True, blank=True, db_column='web_influencer_details_id')
    assumed_timeframe = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'trade_call'
        managed = False  # Don't let Django manage this table

    def __str__(self):
        return f"Trade Call {self.uuid} - {self.asset.symbol if self.asset else 'No Asset'}"


class WebInfluencer(models.Model):
    web_influencer_id = models.BigAutoField(primary_key=True, db_column='web_influencer_id')
    platform = models.CharField(max_length=500)
    url = models.CharField(max_length=1000)
    platform_name = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'web_influencer'
        managed = False

    def __str__(self):
        return f"{self.platform_name or self.platform} - {self.url}"


class WebInfluencerDetails(models.Model):
    web_influencer_details_id = models.BigAutoField(primary_key=True, db_column='web_influencer_details_id')
    web_influencer = models.ForeignKey(WebInfluencer, on_delete=models.DO_NOTHING, db_column='web_influencer_id')
    organization = models.CharField(max_length=500, null=True, blank=True)
    recommendation_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'web_influencer_details'
        managed = False

    def __str__(self):
        return f"Details for {self.web_influencer.platform_name or self.web_influencer.platform}"

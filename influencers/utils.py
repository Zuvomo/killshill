"""
Utility functions for data validation and deduplication
"""
import re
from django.db.models import Q
from .models import Influencer, TradeCall, Asset
from urllib.parse import urlparse
import hashlib


class InfluencerValidator:
    """
    Validates influencer data for quality and uniqueness
    """
    
    @staticmethod
    def validate_platform_url(url, platform):
        """
        Validate that the URL matches the specified platform
        """
        platform_domains = {
            'twitter': ['twitter.com', 'x.com'],
            'telegram': ['t.me', 'telegram.me'],
            'youtube': ['youtube.com', 'youtu.be'],
            'discord': ['discord.com', 'discord.gg'],
        }
        
        if platform.lower() not in platform_domains:
            return False, f"Unknown platform: {platform}"
        
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        
        if domain not in platform_domains[platform.lower()]:
            return False, f"URL does not match {platform} platform"
        
        return True, "Valid platform URL"
    
    @staticmethod
    def extract_username_from_url(url, platform):
        """
        Extract username from platform URL
        """
        try:
            parsed_url = urlparse(url)
            path = parsed_url.path.strip('/')
            
            if platform.lower() == 'twitter':
                # Twitter URLs: https://twitter.com/username or https://x.com/username
                return path
            elif platform.lower() == 'telegram':
                # Telegram URLs: https://t.me/username
                return path
            elif platform.lower() == 'youtube':
                # YouTube URLs: https://youtube.com/@username or https://youtube.com/c/channelname
                if path.startswith('@'):
                    return path[1:]
                elif path.startswith('c/'):
                    return path[2:]
                elif path.startswith('channel/'):
                    return path[8:]
                return path
            elif platform.lower() == 'discord':
                # Discord URLs: https://discord.com/channels/server/channel
                return path
            
            return path
        except Exception:
            return None
    
    @staticmethod
    def check_duplicate_influencer(channel_name, url, platform):
        """
        Check if influencer already exists in database
        """
        # Check by exact URL match
        url_duplicate = Influencer.objects.filter(url__iexact=url).first()
        if url_duplicate:
            return True, f"Influencer with URL already exists: {url_duplicate.channel_name}"
        
        # Check by channel name and platform combination
        name_duplicate = Influencer.objects.filter(
            channel_name__iexact=channel_name,
            platform__iexact=platform
        ).first()
        if name_duplicate:
            return True, f"Influencer with same name and platform already exists: {name_duplicate.channel_name}"
        
        return False, "No duplicate found"
    
    @staticmethod
    def validate_follower_count(follower_count):
        """
        Validate follower count is reasonable
        """
        if follower_count < 0:
            return False, "Follower count cannot be negative"
        
        if follower_count > 500_000_000:  # Max realistic follower count
            return False, "Follower count seems unrealistic"
        
        return True, "Valid follower count"


class TradeCallValidator:
    """
    Validates trade call data for quality and prevents duplicates
    """
    
    @staticmethod
    def validate_trade_call_data(data):
        """
        Validate trade call data structure
        """
        required_fields = ['asset', 'influencer', 'signal']
        errors = []
        
        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"Missing required field: {field}")
        
        # Validate price fields
        price_fields = ['entry_price', 'assumed_entry_price', 'stoploss_price']
        for field in price_fields:
            if field in data and data[field]:
                try:
                    price = float(data[field])
                    if price <= 0:
                        errors.append(f"{field} must be positive")
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a valid number")
        
        # Validate signal type
        valid_signals = ['buy', 'sell', 'long', 'short', 'hold']
        if 'signal' in data and data['signal'].lower() not in valid_signals:
            errors.append(f"Invalid signal type. Must be one of: {', '.join(valid_signals)}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def check_duplicate_trade_call(uuid, influencer_id, asset_id, created_at):
        """
        Check for duplicate trade calls based on various criteria
        """
        # Check by UUID first
        if uuid:
            uuid_duplicate = TradeCall.objects.filter(uuid=uuid).first()
            if uuid_duplicate:
                return True, f"Trade call with UUID already exists: {uuid}"
        
        # Check by influencer, asset, and created_at combination (within 1 hour)
        from datetime import timedelta
        time_range_start = created_at - timedelta(hours=1)
        time_range_end = created_at + timedelta(hours=1)
        
        similar_call = TradeCall.objects.filter(
            influencer_id=influencer_id,
            asset_id=asset_id,
            created_at__range=[time_range_start, time_range_end]
        ).first()
        
        if similar_call:
            return True, f"Similar trade call already exists within 1 hour window"
        
        return False, "No duplicate found"
    
    @staticmethod
    def generate_unique_uuid(base_string):
        """
        Generate a unique UUID based on trade call content
        """
        hash_input = f"{base_string}".encode('utf-8')
        return hashlib.md5(hash_input).hexdigest()


class AssetValidator:
    """
    Validates asset data and prevents duplicates
    """
    
    @staticmethod
    def validate_asset_symbol(symbol):
        """
        Validate asset symbol format
        """
        # Remove special characters and convert to uppercase
        clean_symbol = re.sub(r'[^A-Za-z0-9]', '', symbol).upper()
        
        if len(clean_symbol) < 1:
            return False, "Symbol is too short"
        
        if len(clean_symbol) > 20:
            return False, "Symbol is too long"
        
        return True, clean_symbol
    
    @staticmethod
    def check_duplicate_asset(symbol, name=None):
        """
        Check if asset already exists
        """
        symbol_duplicate = Asset.objects.filter(symbol__iexact=symbol).first()
        if symbol_duplicate:
            return True, f"Asset with symbol already exists: {symbol_duplicate.symbol}"
        
        if name:
            name_duplicate = Asset.objects.filter(name__iexact=name).first()
            if name_duplicate:
                return True, f"Asset with name already exists: {name_duplicate.name}"
        
        return False, "No duplicate found"
    
    @staticmethod
    def validate_asset_data(data):
        """
        Validate complete asset data
        """
        errors = []
        
        # Validate symbol
        if 'symbol' not in data or not data['symbol']:
            errors.append("Symbol is required")
        else:
            is_valid, result = AssetValidator.validate_asset_symbol(data['symbol'])
            if not is_valid:
                errors.append(result)
        
        # Validate asset type
        valid_types = ['crypto', 'stocks', 'forex']
        if 'asset_type' in data and data['asset_type']:
            if data['asset_type'].lower() not in valid_types:
                errors.append(f"Invalid asset type. Must be one of: {', '.join(valid_types)}")
        
        # Validate numerical fields
        numerical_fields = ['market_cap', 'volume', 'current_price']
        for field in numerical_fields:
            if field in data and data[field] is not None:
                try:
                    value = float(data[field])
                    if value < 0:
                        errors.append(f"{field} cannot be negative")
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a valid number")
        
        return len(errors) == 0, errors


class DataDeduplication:
    """
    Handles deduplication of various data types
    """
    
    @staticmethod
    def merge_influencer_profiles(primary_id, duplicate_id):
        """
        Merge duplicate influencer profiles
        """
        try:
            primary = Influencer.objects.get(influencer_id=primary_id)
            duplicate = Influencer.objects.get(influencer_id=duplicate_id)
            
            # Update trade calls to point to primary influencer
            TradeCall.objects.filter(influencer=duplicate).update(influencer=primary)
            
            # Merge any additional data (followers, etc.)
            if not primary.author_name and duplicate.author_name:
                primary.author_name = duplicate.author_name
            
            if not primary.channel_name and duplicate.channel_name:
                primary.channel_name = duplicate.channel_name
            
            primary.save()
            
            # Delete duplicate
            duplicate.delete()
            
            return True, f"Successfully merged influencer {duplicate_id} into {primary_id}"
            
        except Influencer.DoesNotExist:
            return False, "One or both influencers not found"
        except Exception as e:
            return False, f"Error during merge: {str(e)}"
    
    @staticmethod
    def find_potential_duplicates():
        """
        Find potential duplicate influencers based on various criteria
        """
        potential_duplicates = []
        
        # Find duplicates by similar channel names
        influencers = Influencer.objects.all()
        for influencer in influencers:
            if influencer.channel_name:
                # Find similar names (case-insensitive)
                similar = Influencer.objects.filter(
                    channel_name__icontains=influencer.channel_name.lower(),
                    platform=influencer.platform
                ).exclude(influencer_id=influencer.influencer_id)
                
                if similar.exists():
                    potential_duplicates.append({
                        'primary': influencer,
                        'duplicates': list(similar),
                        'reason': 'Similar channel name'
                    })
        
        return potential_duplicates
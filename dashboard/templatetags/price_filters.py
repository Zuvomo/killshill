"""
Custom template filters for price formatting
"""
from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def format_price(value):
    """
    Format price with dynamic decimal places based on value
    """
    if value is None:
        return "-"
    
    try:
        # Convert to float if it's a string
        if isinstance(value, str):
            # Remove any currency symbols and commas
            clean_value = value.replace('$', '').replace(',', '').strip()
            if not clean_value:
                return "-"
            price = float(clean_value)
        else:
            price = float(value)
    except (ValueError, TypeError, InvalidOperation):
        return "-"
    
    # Handle negative prices
    if price < 0:
        return f"-${format_positive_price(abs(price))}"
    
    return f"${format_positive_price(price)}"

def format_positive_price(price):
    """
    Format positive price with appropriate decimal places
    """
    if price >= 1000:
        # High value: 2 decimals with commas
        return f"{price:,.2f}"
    elif price >= 1:
        # Medium value: 4 decimals
        return f"{price:.4f}"
    elif price >= 0.01:
        # Low value: 6 decimals
        return f"{price:.6f}"
    elif price >= 0.0001:
        # Very low value: 8 decimals
        return f"{price:.8f}"
    else:
        # Extremely low value: scientific notation or 10 decimals
        if price == 0:
            return "0.00"
        return f"{price:.10f}".rstrip('0').rstrip('.')

@register.filter
def format_percentage(value):
    """
    Format percentage with 2 decimal places and % sign
    """
    if value is None:
        return "-"
    
    try:
        if isinstance(value, str):
            # Remove % sign if present
            clean_value = value.replace('%', '').strip()
            if not clean_value:
                return "-"
            pct = float(clean_value)
        else:
            pct = float(value)
        
        # Color coding for positive/negative
        if pct > 0:
            return f"+{pct:.2f}%"
        else:
            return f"{pct:.2f}%"
    except (ValueError, TypeError):
        return "-"

@register.filter
def format_volume(value):
    """
    Format volume with K, M, B abbreviations
    """
    if value is None:
        return "-"
    
    try:
        volume = float(value)
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

@register.filter
def format_market_cap(value):
    """
    Format market cap with appropriate abbreviations
    """
    return format_volume(value)  # Same logic as volume

@register.filter
def format_number(value):
    """
    Format large numbers with commas
    """
    if value is None:
        return "-"
    
    try:
        num = float(value)
        if num.is_integer():
            return f"{int(num):,}"
        else:
            return f"{num:,.2f}"
    except (ValueError, TypeError):
        return "-"

@register.filter
def get_entry_price(signal):
    """Get best available entry price - actual if available, otherwise assumed"""
    if signal.entry_price and signal.entry_price.strip() and signal.entry_price != "0":
        return {"price": signal.entry_price, "is_assumed": False}
    elif signal.assumed_entry_price:
        return {"price": signal.assumed_entry_price, "is_assumed": True}
    return {"price": None, "is_assumed": False}

@register.filter 
def get_target_price(signal):
    """Get best available target price - actual if available, otherwise assumed"""
    # Check for valid target_first (not None and not 0)
    if signal.target_first is not None and signal.target_first > 0:
        return {"price": signal.target_first, "is_assumed": False}
    elif signal.assumed_target is not None and signal.assumed_target > 0:
        return {"price": signal.assumed_target, "is_assumed": True}
    return {"price": None, "is_assumed": False}

@register.filter
def get_stoploss_price(signal):
    """Get stop loss price info"""
    if signal.stoploss_price is not None and signal.stoploss_price > 0:
        return {"price": signal.stoploss_price, "is_assumed": False}
    return {"price": None, "is_assumed": False}

@register.filter
def get_timeframe(signal):
    """Get timeframe info - check if timeframe was assumed or actual"""
    if signal.timeframe:
        # Check if this timeframe was assumed or actual
        is_assumed = signal.assumed_timeframe == 'True'
        return {"value": signal.timeframe, "is_assumed": is_assumed, "type": "date"}
    return {"value": None, "is_assumed": False, "type": None}

@register.filter
def calculate_credibility(signal):
    """
    Calculate credibility based on trading outcome:
    - 1: Target hit within timeframe
    - 0: Stop loss hit OR no target/stoploss hit
    - None: Active trade (not concluded)
    """
    if not signal:
        return None
    
    # Check if trade is still active/not concluded
    if not signal.done:
        return None
    
    # If target was hit within timeframe = credibility 1
    if signal.target_hit:
        # If timeframe was specified, check if target was hit within timeframe
        if signal.timeframe and signal.created_at:
            # For now, assume if target_hit is True and trade is done, it was within timeframe
            # You might want to add more sophisticated timeframe checking here
            return 1
        # If no timeframe specified but target hit
        return 1
    
    # If stop loss hit or neither target nor stoploss hit = credibility 0
    if signal.stoploss_hit or (not signal.target_hit and not signal.stoploss_hit):
        return 0
    
    # Default case for incomplete data
    return None

@register.filter
def credibility_display(signal):
    """
    Display credibility in user-friendly format
    """
    credibility = calculate_credibility(signal)
    
    if credibility is None:
        return {
            "value": "Pending",
            "class": "text-warning",
            "description": "Trade outcome pending"
        }
    elif credibility == 1:
        return {
            "value": "Success",
            "class": "text-success",
            "description": "Target achieved"
        }
    else:
        return {
            "value": "Failed",
            "class": "text-danger", 
            "description": "Target not achieved"
        }

@register.filter
def influencer_credibility_score(influencer):
    """
    Calculate overall credibility score for an influencer
    Based on ratio of successful calls to total concluded calls
    """
    if not influencer:
        return None
    
    # Get all concluded calls for this influencer
    concluded_calls = influencer.tradecall_set.filter(done=True)
    
    if not concluded_calls.exists():
        return None
    
    total_calls = concluded_calls.count()
    successful_calls = concluded_calls.filter(target_hit=True).count()
    
    if total_calls == 0:
        return None
    
    credibility_percentage = (successful_calls / total_calls) * 100
    
    return {
        "percentage": round(credibility_percentage, 1),
        "successful": successful_calls,
        "total": total_calls,
        "class": "text-success" if credibility_percentage >= 70 else "text-warning" if credibility_percentage >= 50 else "text-danger"
    }

@register.filter
def smart_timeframe_display(signal):
    """
    Smart timeframe display that handles actual vs assumed timeframes
    """
    if not signal:
        return {"timeframe": "N/A", "is_assumed": False}
    
    # Check if we have an actual timeframe from signal
    if signal.timeframe:
        return {
            "timeframe": signal.timeframe.strftime("%b %d, %Y") if hasattr(signal.timeframe, 'strftime') else str(signal.timeframe),
            "label": "Target Date",
            "is_assumed": False
        }
    
    # Check assumed_timeframe field (assuming it's a boolean or string indicator)
    if hasattr(signal, 'assumed_timeframe') and signal.assumed_timeframe:
        if signal.assumed_timeframe == "True" or signal.assumed_timeframe is True:
            return {
                "timeframe": "Short-term (est.)",
                "label": "Est. Timeframe", 
                "is_assumed": True,
                "tooltip": "Timeframe estimated based on signal type"
            }
        else:
            # If assumed_timeframe contains actual timeframe text
            return {
                "timeframe": signal.assumed_timeframe,
                "label": "Est. Timeframe",
                "is_assumed": True,
                "tooltip": "Timeframe estimated based on signal analysis"
            }
    
    return {"timeframe": "N/A", "label": "N/A", "is_assumed": False}

@register.filter
def signal_data_quality(signal):
    """
    Calculate signal data quality score and return quality indicators
    """
    if not signal:
        return {"score": 0, "quality": "unknown", "indicators": []}
    
    score = 0
    indicators = []
    
    # Entry price quality (20 points)
    if signal.entry_price and signal.entry_price.strip() and signal.entry_price != "0":
        score += 20
        indicators.append({"type": "entry", "status": "actual", "text": "Actual entry price provided"})
    elif signal.assumed_entry_price:
        score += 10
        indicators.append({"type": "entry", "status": "estimated", "text": "Entry price estimated from market data"})
    
    # Target quality (30 points)
    targets = [signal.target_first, signal.target_second, signal.target_third]
    actual_targets = [t for t in targets if t and t > 0]
    
    if len(actual_targets) >= 2:
        score += 30
        indicators.append({"type": "target", "status": "excellent", "text": f"{len(actual_targets)} target levels specified"})
    elif len(actual_targets) == 1:
        score += 25
        indicators.append({"type": "target", "status": "good", "text": "Target price specified"})
    elif signal.assumed_target:
        score += 15
        indicators.append({"type": "target", "status": "estimated", "text": "Target estimated (10% gain)"})
    
    # Stop loss quality (20 points)
    if signal.stoploss_price:
        score += 20
        indicators.append({"type": "stoploss", "status": "actual", "text": "Stop loss specified"})
    
    # Timeframe quality (20 points)
    if signal.timeframe:
        score += 20
        indicators.append({"type": "timeframe", "status": "actual", "text": "Target timeframe specified"})
    elif hasattr(signal, 'assumed_timeframe') and signal.assumed_timeframe:
        score += 10
        indicators.append({"type": "timeframe", "status": "estimated", "text": "Timeframe estimated"})
    
    # Signal content quality (10 points)
    content_length = len(signal.signal or signal.text or signal.description or "")
    if content_length > 100:
        score += 10
        indicators.append({"type": "content", "status": "detailed", "text": "Detailed signal analysis"})
    elif content_length > 20:
        score += 5
        indicators.append({"type": "content", "status": "basic", "text": "Basic signal information"})
    
    # Determine quality level
    if score >= 85:
        quality = "excellent"
    elif score >= 70:
        quality = "good"
    elif score >= 50:
        quality = "fair"
    elif score >= 30:
        quality = "poor"
    else:
        quality = "incomplete"
    
    return {
        "score": score,
        "quality": quality,
        "indicators": indicators,
        "color_class": {
            "excellent": "text-success",
            "good": "text-info", 
            "fair": "text-warning",
            "poor": "text-danger",
            "incomplete": "text-muted"
        }.get(quality, "text-muted")
    }
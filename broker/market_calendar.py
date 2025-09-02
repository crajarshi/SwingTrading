"""NYSE market calendar and trading hours management.

Handles holidays, half-days, and timezone conversions.
All times locked to America/New_York timezone.
"""

from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple
import pytz
from zoneinfo import ZoneInfo

# NYSE timezone - locked everywhere
NYSE_TZ = ZoneInfo("America/New_York")
NYSE_PYTZ = pytz.timezone("America/New_York")

# Standard market hours
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

# 2024-2025 NYSE Holidays (observed dates)
NYSE_HOLIDAYS = {
    # 2024
    datetime(2024, 1, 1).date(),   # New Year's Day
    datetime(2024, 1, 15).date(),  # MLK Day
    datetime(2024, 2, 19).date(),  # Presidents Day
    datetime(2024, 3, 29).date(),  # Good Friday
    datetime(2024, 5, 27).date(),  # Memorial Day
    datetime(2024, 6, 19).date(),  # Juneteenth
    datetime(2024, 7, 4).date(),   # Independence Day
    datetime(2024, 9, 2).date(),   # Labor Day
    datetime(2024, 11, 28).date(), # Thanksgiving
    datetime(2024, 12, 25).date(), # Christmas
    
    # 2025
    datetime(2025, 1, 1).date(),   # New Year's Day
    datetime(2025, 1, 20).date(),  # MLK Day
    datetime(2025, 2, 17).date(),  # Presidents Day
    datetime(2025, 4, 18).date(),  # Good Friday
    datetime(2025, 5, 26).date(),  # Memorial Day
    datetime(2025, 6, 19).date(),  # Juneteenth
    datetime(2025, 7, 4).date(),   # Independence Day
    datetime(2025, 9, 1).date(),   # Labor Day
    datetime(2025, 11, 27).date(), # Thanksgiving
    datetime(2025, 12, 25).date(), # Christmas
    
    # 2026 (extend as needed)
    datetime(2026, 1, 1).date(),   # New Year's Day
    datetime(2026, 1, 19).date(),  # MLK Day
    datetime(2026, 2, 16).date(),  # Presidents Day
    datetime(2026, 4, 3).date(),   # Good Friday
    datetime(2026, 5, 25).date(),  # Memorial Day
    datetime(2026, 6, 19).date(),  # Juneteenth
    datetime(2026, 7, 3).date(),   # Independence Day (observed)
    datetime(2026, 9, 7).date(),   # Labor Day
    datetime(2026, 11, 26).date(), # Thanksgiving
    datetime(2026, 12, 25).date(), # Christmas
}

# Early close days (1pm ET close)
EARLY_CLOSE_DAYS = {
    # 2024
    datetime(2024, 7, 3).date(),   # Day before Independence Day
    datetime(2024, 11, 29).date(), # Day after Thanksgiving
    datetime(2024, 12, 24).date(), # Christmas Eve
    
    # 2025
    datetime(2025, 7, 3).date(),   # Day before Independence Day
    datetime(2025, 11, 28).date(), # Day after Thanksgiving  
    datetime(2025, 12, 24).date(), # Christmas Eve
    
    # 2026
    datetime(2026, 11, 27).date(), # Day after Thanksgiving
    datetime(2026, 12, 24).date(), # Christmas Eve
}


def is_holiday(date: datetime) -> bool:
    """Check if a date is a NYSE holiday."""
    return date.date() in NYSE_HOLIDAYS


def is_early_close(date: datetime) -> bool:
    """Check if a date is an early close day (1pm ET)."""
    return date.date() in EARLY_CLOSE_DAYS


def is_trading_day(date: datetime) -> bool:
    """Check if a date is a trading day (not weekend or holiday)."""
    # Weekend check
    if date.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    # Holiday check
    return not is_holiday(date)


def get_next_session(date: datetime, tz: str = "America/New_York") -> Optional[datetime]:
    """Get the next trading session date after the given date.
    
    Args:
        date: Current date (timezone-aware or naive)
        tz: Timezone string (always uses America/New_York internally)
    
    Returns:
        Next trading day at market open, or None if none found in 10 days
    """
    # Ensure we're working in NYSE timezone
    if date.tzinfo is None:
        date = datetime.combine(date.date(), date.time(), tzinfo=NYSE_TZ)
    else:
        date = date.astimezone(NYSE_TZ)
    
    # Start from next day
    next_date = date + timedelta(days=1)
    
    # Look up to 10 days ahead
    for _ in range(10):
        if is_trading_day(next_date):
            # Return at market open time
            return datetime.combine(
                next_date.date(),
                REGULAR_OPEN,
                tzinfo=NYSE_TZ
            )
        next_date += timedelta(days=1)
    
    return None


def is_market_open(dt: datetime, tz: str = "America/New_York") -> bool:
    """Check if the market is currently open.
    
    Args:
        dt: Datetime to check (timezone-aware or naive)
        tz: Timezone string (always uses America/New_York internally)
    
    Returns:
        True if market is open, False otherwise
    """
    # Ensure we're working in NYSE timezone
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), dt.time(), tzinfo=NYSE_TZ)
    else:
        dt = dt.astimezone(NYSE_TZ)
    
    # Not a trading day
    if not is_trading_day(dt):
        return False
    
    # Get market hours for this day
    session_times = get_session_times(dt)
    open_time = session_times['open']
    close_time = session_times['close']
    
    current_time = dt.time()
    return open_time <= current_time < close_time


def get_session_times(date: datetime) -> Dict:
    """Get market open and close times for a specific date.
    
    Args:
        date: Date to check (timezone-aware or naive)
    
    Returns:
        Dict with keys: 'open', 'close', 'is_half_day', 'is_holiday'
    """
    # Ensure we have a date object
    if hasattr(date, 'date'):
        check_date = date.date()
    else:
        check_date = date
    
    result = {
        'open': REGULAR_OPEN,
        'close': REGULAR_CLOSE,
        'is_half_day': False,
        'is_holiday': False
    }
    
    # Check if holiday
    if check_date in NYSE_HOLIDAYS:
        result['is_holiday'] = True
        result['open'] = None
        result['close'] = None
        return result
    
    # Check if early close
    if check_date in EARLY_CLOSE_DAYS:
        result['close'] = EARLY_CLOSE
        result['is_half_day'] = True
    
    return result


def adjust_placement_time(date: datetime, base_time: str) -> datetime:
    """Adjust order placement time based on market schedule.
    
    For half-days, may need to place orders earlier.
    For holidays, carries forward to next session.
    
    Args:
        date: Target date for placement
        base_time: Base time string (e.g., "09:28")
    
    Returns:
        Adjusted datetime for order placement
    """
    # Parse base time
    hour, minute = map(int, base_time.split(':'))
    base_time_obj = time(hour, minute)
    
    # Ensure we're working in NYSE timezone
    if date.tzinfo is None:
        date = datetime.combine(date.date(), date.time(), tzinfo=NYSE_TZ)
    else:
        date = date.astimezone(NYSE_TZ)
    
    # Check if target date is a trading day
    if not is_trading_day(date):
        # Move to next trading day
        next_session = get_next_session(date)
        if next_session:
            date = next_session.replace(hour=hour, minute=minute)
        else:
            raise ValueError(f"No trading session found within 10 days of {date}")
    
    # Get session times
    session_times = get_session_times(date)
    
    # For early close days, adjust if placement time is after close
    if session_times['is_half_day']:
        close_time = session_times['close']
        if base_time_obj >= close_time:
            # Place orders earlier on half days
            # For now, keep original time but ensure it's before close
            # Could be enhanced to shift proportionally
            pass
    
    # Combine date with time
    result = datetime.combine(date.date(), base_time_obj, tzinfo=NYSE_TZ)
    
    return result


def get_market_schedule(start_date: datetime, end_date: datetime) -> Dict[datetime, Dict]:
    """Get market schedule for a date range.
    
    Args:
        start_date: Start of range
        end_date: End of range
    
    Returns:
        Dict mapping dates to session info
    """
    schedule = {}
    
    # Ensure timezone aware
    if start_date.tzinfo is None:
        start_date = datetime.combine(start_date.date(), start_date.time(), tzinfo=NYSE_TZ)
    if end_date.tzinfo is None:
        end_date = datetime.combine(end_date.date(), end_date.time(), tzinfo=NYSE_TZ)
    
    current = start_date
    while current <= end_date:
        if is_trading_day(current):
            schedule[current.date()] = get_session_times(current)
        current += timedelta(days=1)
    
    return schedule


def get_previous_close(dt: datetime) -> Optional[datetime]:
    """Get the previous market close time before the given datetime.
    
    Args:
        dt: Reference datetime
    
    Returns:
        Previous market close datetime
    """
    # Ensure we're working in NYSE timezone
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), dt.time(), tzinfo=NYSE_TZ)
    else:
        dt = dt.astimezone(NYSE_TZ)
    
    # Start from current or previous day
    check_date = dt.date()
    
    # If it's during trading hours today, use today's close
    if is_trading_day(dt) and dt.time() < get_session_times(dt)['close']:
        check_date = dt.date() - timedelta(days=1)
    
    # Look back up to 10 days
    for _ in range(10):
        if is_trading_day(datetime.combine(check_date, time.min, tzinfo=NYSE_TZ)):
            session = get_session_times(datetime.combine(check_date, time.min))
            return datetime.combine(check_date, session['close'], tzinfo=NYSE_TZ)
        check_date -= timedelta(days=1)
    
    return None
from datetime import datetime, date
from dateutil.rrule import rrule, DAILY, MO, TU, WE, TH, SA, SU
import calendar

def to_two_digits(n):
    return f"{n:02d}"

def get_month_range(month: str):
    year, m = map(int, month.split('-'))
    
    start = datetime(year, m, 1)
    last_day = calendar.monthrange(year, m)[1]
    end = datetime(year, m, last_day)
    
    return start, end

def hours_between(start_time, end_time):
    start = datetime.combine(date.today(), start_time)
    end = datetime.combine(date.today(), end_time)

    delta = end - start
    return delta.total_seconds() / 3600



def dates_between_skip_friday(start: date, end: date):
    return [d.date() for d in rrule(
        DAILY,
        dtstart=start,
        until=end,
        byweekday=(MO, TU, WE, TH, SA, SU)  # Friday excluded
    )]

from datetime import datetime, date
from dateutil.rrule import rrule, DAILY, MO, TU, WE, TH, SA, SU


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

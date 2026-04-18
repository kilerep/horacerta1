from datetime import date, datetime, time

from django.utils import timezone


def format_punch_time(local_dt):
    return local_dt.strftime("%H:%M")


def format_hhmm(total_seconds):
    total_minutes = int(round(total_seconds / 60))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def compute_day_total(local_datetimes):
    ordered = sorted(local_datetimes)
    minute_aligned = [dt.replace(second=0, microsecond=0) for dt in ordered]
    total_seconds = 0
    for idx in range(0, len(minute_aligned) - 1, 2):
        delta = int((minute_aligned[idx + 1] - minute_aligned[idx]).total_seconds())
        if delta > 0:
            total_seconds += delta
    return total_seconds, bool(len(minute_aligned) % 2)


def filter_punches_by_period(base_qs, date_from_raw, date_to_raw, field_name="timestamp"):
    date_from = None
    date_to = None

    if date_from_raw:
        try:
            date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
        except ValueError:
            date_from = None

    if date_to_raw:
        try:
            date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
        except ValueError:
            date_to = None

    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    if date_from:
        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        base_qs = base_qs.filter(**{f"{field_name}__gte": start_dt})

    if date_to:
        end_dt = timezone.make_aware(datetime.combine(date_to, time.max))
        base_qs = base_qs.filter(**{f"{field_name}__lte": end_dt})

    return base_qs, date_from, date_to


def build_daily_summary(punches, min_punch_columns=4):
    by_day = {}
    for punch in punches:
        local_ts = timezone.localtime(punch.timestamp)
        day = local_ts.date()
        by_day.setdefault(day, []).append({"local_ts": local_ts})

    rows = []
    max_columns = min_punch_columns
    for day in sorted(by_day.keys(), reverse=True):
        points = sorted(by_day[day], key=lambda item: item["local_ts"])
        max_columns = max(max_columns, len(points))

        total_seconds, is_incomplete = compute_day_total([item["local_ts"] for item in points])

        rows.append(
            {
                "date": day,
                "punches_count": len(points),
                "punch_times": [format_punch_time(item["local_ts"]) for item in points],
                "notes_summary": "",
                "total_seconds": total_seconds,
                "total_hours_hhmm": format_hhmm(total_seconds),
                "status": "INCOMPLETO" if is_incomplete else "OK",
                "is_incomplete": is_incomplete,
            }
        )

    max_columns = max(max_columns, min_punch_columns)
    for row in rows:
        row["punch_columns"] = row["punch_times"] + ["-"] * (max_columns - len(row["punch_times"]))

    return rows, max_columns

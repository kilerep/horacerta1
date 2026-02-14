from datetime import date, datetime, time

from django.utils import timezone


def format_hhmm(total_seconds):
    total_minutes = int(total_seconds // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


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
        by_day.setdefault(day, []).append(
            {
                "local_ts": local_ts,
                "note": (punch.note or "").strip(),
            }
        )

    rows = []
    max_columns = min_punch_columns
    for day in sorted(by_day.keys(), reverse=True):
        points = sorted(by_day[day], key=lambda item: item["local_ts"])
        max_columns = max(max_columns, len(points))

        total_seconds = 0
        for idx in range(0, len(points) - 1, 2):
            total_seconds += int((points[idx + 1]["local_ts"] - points[idx]["local_ts"]).total_seconds())

        notes = [item["note"] for item in points if item["note"]]
        rows.append(
            {
                "date": day,
                "punches_count": len(points),
                "punch_times": [item["local_ts"].strftime("%H:%M:%S") for item in points],
                "notes_summary": " | ".join(notes[:3]) + (" ..." if len(notes) > 3 else ""),
                "total_seconds": total_seconds,
                "total_hours_decimal": round(total_seconds / 3600, 2),
                "total_hours_hhmm": format_hhmm(total_seconds),
                "status": "INCOMPLETO" if len(points) % 2 else "OK",
                "is_incomplete": bool(len(points) % 2),
            }
        )

    max_columns = max(max_columns, min_punch_columns)
    for row in rows:
        row["punch_columns"] = row["punch_times"] + ["-"] * (max_columns - len(row["punch_times"]))

    return rows, max_columns


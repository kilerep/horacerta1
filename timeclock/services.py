from datetime import date, datetime, time
from math import atan2, cos, radians, sin, sqrt

from django.utils import timezone

from companies.models import CompanyAttendancePolicy, CompanyAuthorizedLocation


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
        if getattr(punch, "is_cancelled", False):
            continue
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


def _punch_status(punch):
    return "cancelled" if punch.is_cancelled else "active"


def _require_correction_reason(reason):
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("Informe um motivo para registrar a auditoria.")
    return clean_reason


def change_punch_time(*, punch, admin_user, new_datetime, reason):
    from timeclock.models import PunchCorrectionLog

    reason = _require_correction_reason(reason)
    if new_datetime is None:
        raise ValueError("Informe o novo horario.")
    if timezone.is_naive(new_datetime):
        new_datetime = timezone.make_aware(new_datetime, timezone.get_current_timezone())

    old_datetime = punch.timestamp
    old_status = _punch_status(punch)
    punch.timestamp = new_datetime
    punch.save(update_fields=["timestamp"])
    return PunchCorrectionLog.objects.create(
        punch=punch,
        admin_user=admin_user,
        action_type=PunchCorrectionLog.ActionType.TIME_CHANGED,
        old_datetime=old_datetime,
        new_datetime=punch.timestamp,
        old_status=old_status,
        new_status=_punch_status(punch),
        reason=reason,
    )


def cancel_punch(*, punch, admin_user, reason):
    from timeclock.models import PunchCorrectionLog

    reason = _require_correction_reason(reason)
    old_status = _punch_status(punch)
    old_datetime = punch.timestamp
    if not punch.is_cancelled:
        punch.is_cancelled = True
        punch.cancelled_at = timezone.now()
        punch.cancelled_by = admin_user
        punch.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])
    return PunchCorrectionLog.objects.create(
        punch=punch,
        admin_user=admin_user,
        action_type=PunchCorrectionLog.ActionType.CANCELLED,
        old_datetime=old_datetime,
        new_datetime=punch.timestamp,
        old_status=old_status,
        new_status=_punch_status(punch),
        reason=reason,
    )


def restore_punch(*, punch, admin_user, reason):
    from timeclock.models import PunchCorrectionLog

    reason = _require_correction_reason(reason)
    old_status = _punch_status(punch)
    old_datetime = punch.timestamp
    if punch.is_cancelled:
        punch.is_cancelled = False
        punch.cancelled_at = None
        punch.cancelled_by = None
        punch.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])
    return PunchCorrectionLog.objects.create(
        punch=punch,
        admin_user=admin_user,
        action_type=PunchCorrectionLog.ActionType.RESTORED,
        old_datetime=old_datetime,
        new_datetime=punch.timestamp,
        old_status=old_status,
        new_status=_punch_status(punch),
        reason=reason,
    )


def add_punch_admin_note(*, punch, admin_user, note, reason=None):
    from timeclock.models import PunchCorrectionLog

    clean_note = (note or "").strip()
    if not clean_note:
        raise ValueError("Informe a observacao administrativa.")
    clean_reason = _require_correction_reason(reason)
    old_status = _punch_status(punch)
    old_datetime = punch.timestamp
    punch.admin_note = clean_note
    punch.save(update_fields=["admin_note"])
    return PunchCorrectionLog.objects.create(
        punch=punch,
        admin_user=admin_user,
        action_type=PunchCorrectionLog.ActionType.ADMIN_NOTE_ADDED,
        old_datetime=old_datetime,
        new_datetime=punch.timestamp,
        old_status=old_status,
        new_status=_punch_status(punch),
        reason=clean_reason,
    )


def haversine_distance_meters(lat1, lon1, lat2, lon2):
    earth_radius_m = 6371000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return earth_radius_m * c


def evaluate_punch_confidence(contract, latitude=None, longitude=None, accuracy_m=None):
    policy = CompanyAttendancePolicy.objects.filter(company=contract.company).first()
    validation_mode = policy.validation_mode if policy else CompanyAttendancePolicy.ValidationMode.FREE
    requires_location = bool(policy and policy.require_location) or validation_mode == CompanyAttendancePolicy.ValidationMode.GEOLOCATION

    result = {
        "validation_method": "FREE_POLICY",
        "confidence_status": "FREE",
        "validated_location": None,
        "distance_to_location_m": None,
    }

    if validation_mode == CompanyAttendancePolicy.ValidationMode.FREE and not requires_location:
        return result

    if not requires_location:
        if validation_mode == CompanyAttendancePolicy.ValidationMode.PRESENTIAL_QR:
            result["validation_method"] = "PRESENTIAL_QR_PENDING"
        return result

    result["validation_method"] = "GEOLOCATION"
    locations_qs = CompanyAuthorizedLocation.objects.filter(company=contract.company, is_active=True).order_by("name")
    if policy and policy.default_location_id:
        default_location = locations_qs.filter(id=policy.default_location_id).first()
        locations = [default_location] if default_location else list(locations_qs)
    else:
        locations = list(locations_qs)
    if not locations:
        result["confidence_status"] = "FREE"
        return result

    if latitude is None or longitude is None:
        result["confidence_status"] = "NO_LOCATION"
        return result

    nearest_location = None
    nearest_distance = None
    for item in locations:
        distance = haversine_distance_meters(
            float(latitude),
            float(longitude),
            float(item.latitude),
            float(item.longitude),
        )
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_location = item

    if nearest_location:
        result["validated_location"] = nearest_location
        result["distance_to_location_m"] = round(float(nearest_distance), 2)

    if accuracy_m is not None:
        try:
            accuracy_value = float(accuracy_m)
        except (TypeError, ValueError):
            accuracy_value = None
        if accuracy_value and accuracy_value > 200:
            result["confidence_status"] = "IMPRECISE"
            return result

    radius_limit = None
    if nearest_location:
        radius_limit = float(nearest_location.allowed_radius_m)
    if (radius_limit is None or radius_limit <= 0) and policy and policy.default_allowed_radius_m:
        radius_limit = float(policy.default_allowed_radius_m)
    if radius_limit is None or radius_limit <= 0:
        radius_limit = 120.0

    if nearest_location and nearest_distance is not None and nearest_distance <= radius_limit:
        result["confidence_status"] = "ON_SITE"
    else:
        result["confidence_status"] = "OUT_OF_RADIUS"

    return result

"""Store opening hours (section 2 of the policy manual), computed instead of left to the model."""
from datetime import datetime, time, timedelta, timezone

# Campo Grande has been at UTC-4 all year since Brazil dropped daylight saving in 2019.
# A fixed offset also avoids depending on the tzdata package on Windows.
STORE_TIMEZONE = timezone(timedelta(hours=-4))

# Keyed by datetime.weekday(); Sunday is closed. Holidays are not in the data.
OPENING_HOURS = {
    0: (time(9), time(18)),
    1: (time(9), time(18)),
    2: (time(9), time(18)),
    3: (time(9), time(18)),
    4: (time(9), time(18)),
    5: (time(9), time(13)),
}


# Indexed by datetime.weekday().
_WEEKDAYS = (
    "na segunda-feira",
    "na terça-feira",
    "na quarta-feira",
    "na quinta-feira",
    "na sexta-feira",
    "no sábado",
    "no domingo",
)


def store_now() -> datetime:
    return datetime.now(STORE_TIMEZONE)


def is_open(moment: datetime) -> bool:
    hours = OPENING_HOURS.get(moment.weekday())
    return hours is not None and hours[0] <= moment.time() < hours[1]


def next_opening(moment: datetime) -> datetime:
    """The first opening strictly after a moment when the store is closed."""
    for days_ahead in range(8):
        day = moment + timedelta(days=days_ahead)
        hours = OPENING_HOURS.get(day.weekday())
        if hours is None:
            continue
        opening = day.replace(hour=hours[0].hour, minute=0, second=0, microsecond=0)
        if opening > moment:
            return opening
    raise ValueError("OPENING_HOURS has no opening day")


def closed_notice(moment: datetime) -> str | None:
    """Customer-facing notice with the return time, required by section 7.1 of the manual."""
    if is_open(moment):
        return None
    opening = next_opening(moment)
    days_ahead = (opening.date() - moment.date()).days
    day = {0: "hoje", 1: "amanhã"}.get(days_ahead, _WEEKDAYS[opening.weekday()])
    return (
        f"Estamos fora do horário de atendimento, e a equipe da loja volta {day} às "
        f"{opening:%H:%M}. Enquanto isso, sigo te ajudando por aqui!"
    )


def describe_status(moment: datetime) -> str:
    now = moment.strftime("%A, %Y-%m-%d %H:%M")
    if is_open(moment):
        closing = OPENING_HOURS[moment.weekday()][1]
        return f"Now: {now}. The store is OPEN until {closing:%H:%M}."
    opening = next_opening(moment).strftime("%A, %Y-%m-%d at %H:%M")
    return f"Now: {now}. The store is CLOSED. It reopens on {opening}."

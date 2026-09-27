from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

def local_time(value, fold=""):
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Bitte einen gültigen Termin eingeben.") from None
    if naive.tzinfo:
        return naive.timestamp()
    valid = []
    for f in (0, 1):
        aware = naive.replace(tzinfo=BERLIN, fold=f)
        if datetime.fromtimestamp(aware.timestamp(), BERLIN).replace(tzinfo=None) == naive:
            valid.append(aware)
    if not valid:
        raise ValueError("Diese Uhrzeit existiert wegen der Sommerzeitumstellung nicht.")
    if len(valid) == 2 and valid[0].utcoffset() != valid[1].utcoffset():
        if str(fold) not in ("0", "1"):
            raise ValueError("Diese Uhrzeit kommt zweimal vor. Bitte Sommerzeit oder Normalzeit wählen.")
        return valid[int(fold)].timestamp()
    return valid[0].timestamp()

def display(value, pattern="%d.%m.%Y · %H:%M"):
    return datetime.fromtimestamp(value, BERLIN).strftime(pattern) if value is not None else "—"

def week_bounds(offset=0):
    now = datetime.now(BERLIN)
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=offset)
    return start.timestamp(), (start + timedelta(days=7)).timestamp()

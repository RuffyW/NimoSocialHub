from sqlalchemy import select
from .models import Metric, Observation

DEFINITIONS = {
    "views": ("Aufrufe", "Abspielen oder Anzeigen auf Instagram; wiederholte Aufrufe sind möglich.", "Anzahl", "both"),
    "reach": ("Reichweite", "Geschätzte Anzahl eindeutiger erreichter Konten. Nicht über Beiträge oder Tage summieren.", "Konten", "both"),
    "likes": ("Gefällt mir", "Gefällt-mir-Angaben; organische Beitragswerte und Kontowerte getrennt betrachten.", "Anzahl", "both"),
    "comments": ("Kommentare", "Anzahl der Kommentare.", "Anzahl", "both"),
    "saved": ("Gespeichert", "Wie oft dieser Beitrag gespeichert wurde.", "Anzahl", "publication"),
    "saves": ("Gespeichert (Konto)", "Speicherungen im angegebenen Kontoberichtszeitraum.", "Anzahl", "account"),
    "shares": ("Geteilt", "Anzahl der Teilungen.", "Anzahl", "both"),
    "total_interactions": ("Interaktionen", "Plattform-Gesamtwert; Kontodaten können beworbene Inhalte einschließen.", "Anzahl", "both"),
    "accounts_engaged": ("Interagierende Konten", "Geschätzte eindeutige Konten mit Interaktionen, gegebenenfalls einschließlich Werbung.", "Konten", "account"),
    "followers_count": ("Followerbestand", "Aktueller Bestand zum Messzeitpunkt, keine Anzahl neuer Follower.", "Konten", "account"),
    "follows": ("Neue Follower", "Zugänge innerhalb des angegebenen Zeitraums; kann unter 100 Followern fehlen.", "Konten", "account"),
    "unfollows": ("Abgänge", "Abgänge innerhalb des angegebenen Zeitraums; kann unter 100 Followern fehlen.", "Konten", "account"),
    "ig_reels_avg_watch_time": ("Ø Wiedergabedauer", "Durchschnittliche Reel-Wiedergabedauer laut API, Millisekunden.", "ms", "publication"),
    "ig_reels_video_view_total_time": ("Gesamte Wiedergabedauer", "Gesamte Reel-Wiedergabedauer einschließlich Wiederholungen, Millisekunden.", "ms", "publication"),
}

def seed(session):
    for key, (label, description, unit, scope) in DEFINITIONS.items():
        if not session.get(Metric, key):
            session.add(Metric(key=key, label=label, description=description, unit=unit, scope=scope))

def comparable(session, publication, metric, days=7, source="api"):
    target = publication.published_at + days * 86400
    tolerance = (6 if days == 1 else 12) * 3600
    rows = session.scalars(select(Observation).where(
        Observation.publication_id == publication.id, Observation.metric == metric,
        Observation.source == source, Observation.period_start.is_(None),
        Observation.observed_at.between(target-tolerance, target+tolerance),
    )).all()
    return min(rows, key=lambda row: abs(row.observed_at-target), default=None)

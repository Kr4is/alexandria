class BookStatus:
    READING  = 'reading'
    FINISHED = 'finished'
    TBR      = 'tbr'
    PAUSED   = 'paused'
    DNF      = 'dnf'
    PAST     = 'past'  # "Read before": read long ago, never tracked, so it has no dates

    ALL = (READING, FINISHED, TBR, PAUSED, DNF, PAST)

    # Statuses where the book has not been (re)started on a known day: no start date, no stamps.
    UNDATED = (TBR, PAST)

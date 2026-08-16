"""Default seed data for local development.

This is the same dummy dataset the prototype has always shipped with,
now expressed in terms of the domain model instead of raw dicts. Milestone 2
will add admin CRUD so this stops being the only way to populate a store.
"""
from domain.models import Teacher, Subject, Student, Section, Meeting, TimeSlot
from data.store import InMemoryStore

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PERIODS = ["9:00", "11:00", "14:00", "16:00"]  # 4 canonical periods


def build_default_store() -> InMemoryStore:
    store = InMemoryStore()

    teachers = [
        Teacher(id=0, name="Dr. Sharma"),
        Teacher(id=1, name="Prof. Mehta"),
        Teacher(id=2, name="Prof. Joshi"),
        Teacher(id=3, name="Dr. Nair"),
        Teacher(id=4, name="Dr. Verma"),
        Teacher(id=5, name="Prof. Kulkarni"),
        Teacher(id=6, name="Prof. Rao"),
    ]
    store.teachers = {t.id: t for t in teachers}
    by_name = {t.name: t.id for t in teachers}

    subjects = [
        Subject(code="IT301", name="Data Structures"),
        Subject(code="IT302", name="OS Concepts"),
        Subject(code="IT303", name="DBMS"),
        Subject(code="IT304", name="CN Lab"),
    ]
    store.subjects = {s.code: s for s in subjects}

    students = [
        Student(id=0, name="Pranav Waghmare", roll="23101C0006"),
        Student(id=1, name="Vedant Ghodekar", roll="23101C0007"),
        Student(id=2, name="Sujal Jakakure",  roll="23101A0018"),
        Student(id=3, name="Parth Mokashi",   roll="23101B0062"),
    ]
    store.students = {s.id: s for s in students}

    sections = [
        Section(id=0, subject_code="IT301", label="A", teacher_id=by_name["Dr. Sharma"], room="L101", capacity=3,
                meetings=[Meeting("Mon", "9:00"), Meeting("Wed", "9:00")]),
        Section(id=1, subject_code="IT301", label="B", teacher_id=by_name["Prof. Mehta"], room="L102", capacity=3,
                meetings=[Meeting("Tue", "11:00")]),
        Section(id=2, subject_code="IT301", label="C", teacher_id=by_name["Dr. Sharma"], room="L103", capacity=3,
                meetings=[Meeting("Wed", "14:00")]),
        Section(id=3, subject_code="IT302", label="A", teacher_id=by_name["Prof. Joshi"], room="L201", capacity=3,
                meetings=[Meeting("Mon", "11:00")]),
        Section(id=4, subject_code="IT302", label="B", teacher_id=by_name["Dr. Nair"], room="L202", capacity=3,
                meetings=[Meeting("Thu", "9:00")]),
        Section(id=5, subject_code="IT302", label="C", teacher_id=by_name["Prof. Joshi"], room="L203", capacity=3,
                meetings=[Meeting("Fri", "10:00")]),
        Section(id=6, subject_code="IT303", label="A", teacher_id=by_name["Dr. Verma"], room="L301", capacity=3,
                meetings=[Meeting("Tue", "9:00"), Meeting("Thu", "11:00")]),
        Section(id=7, subject_code="IT303", label="B", teacher_id=by_name["Prof. Kulkarni"], room="L302", capacity=3,
                meetings=[Meeting("Wed", "11:00")]),
        Section(id=8, subject_code="IT304", label="A", teacher_id=by_name["Prof. Rao"], room="Lab1", capacity=3,
                meetings=[Meeting("Thu", "14:00")]),
        Section(id=9, subject_code="IT304", label="B", teacher_id=by_name["Prof. Rao"], room="Lab1", capacity=3,
                meetings=[Meeting("Fri", "14:00")]),
    ]
    store.sections = {s.id: s for s in sections}

    store.time_slots = [
        TimeSlot(key=f"{d}|{t}", day=d, time=t, label=f"{d} {t}")
        for d in DAYS for t in PERIODS
    ]

    # Default time-slot preferences — unchanged from the prior prototype.
    store.student_ts_prefs = {
        0: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
            "Wed|11:00": 2, "Wed|14:00": 3, "Thu|9:00": 1, "Thu|14:00": 2,
            "Fri|10:00": 2, "Fri|14:00": 1},
        1: {"Mon|9:00": 3, "Mon|11:00": 1, "Tue|9:00": 2, "Tue|11:00": 1,
            "Wed|11:00": 1, "Wed|14:00": 2, "Thu|9:00": 2, "Thu|14:00": 1,
            "Fri|10:00": 3, "Fri|14:00": 2},
        2: {"Mon|9:00": 2, "Mon|11:00": 2, "Tue|9:00": 3, "Tue|11:00": 4,
            "Wed|11:00": 1, "Wed|14:00": 1, "Thu|9:00": 1, "Thu|14:00": 3,
            "Fri|10:00": 2, "Fri|14:00": 1},
        3: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
            "Wed|11:00": 3, "Wed|14:00": 2, "Thu|9:00": 3, "Thu|14:00": 2,
            "Fri|10:00": 1, "Fri|14:00": 1},
    }

    # Default faculty preferences, per subject — same ranking intent as the
    # prior prototype, now keyed by teacher_id instead of teacher name.
    dr_sharma, prof_mehta = by_name["Dr. Sharma"], by_name["Prof. Mehta"]
    prof_joshi, dr_nair = by_name["Prof. Joshi"], by_name["Dr. Nair"]
    dr_verma, prof_kulkarni = by_name["Dr. Verma"], by_name["Prof. Kulkarni"]

    store.student_faculty_prefs = {
        0: {"IT301": {dr_sharma: 1, prof_mehta: 2},
            "IT302": {prof_joshi: 1, dr_nair: 2},
            "IT303": {dr_verma: 1, prof_kulkarni: 2}},
        1: {"IT301": {prof_mehta: 1, dr_sharma: 3},
            "IT302": {dr_nair: 3, prof_joshi: 1},
            "IT303": {prof_kulkarni: 1, dr_verma: 2}},
        2: {"IT301": {dr_sharma: 1, prof_mehta: 1},
            "IT302": {prof_joshi: 1, dr_nair: 1},
            "IT303": {dr_verma: 2, prof_kulkarni: 1}},
        3: {"IT301": {prof_mehta: 2, dr_sharma: 1},
            "IT302": {dr_nair: 1, prof_joshi: 2},
            "IT303": {prof_kulkarni: 3, dr_verma: 1}},
        # IT304 intentionally omitted for every student: both its sections
        # are taught by the same teacher (Prof. Rao), so there is nothing
        # to rank — see api/catalog.py's faculty-by-subject endpoint.
    }

    return store

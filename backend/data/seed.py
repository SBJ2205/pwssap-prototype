"""Default seed data for local development and demos.

This is still the same kind of dummy dataset the prototype has always
shipped with, just a larger MVP-demo-sized roster/catalog (more teachers,
subjects, students, and sections) so the UI has enough variety to look
populated. Admin CRUD (see api/admin.py) can now add/edit/remove data on
top of this bootstrap, but this file remains the only *default* dataset a
fresh in-memory store starts with.

The original 4 students' hand-authored preferences are kept byte-for-byte
identical to avoid changing any previously-observed solver behavior for
them. New students' preferences are generated with a small deterministic
(fixed-seed) helper below, purely to avoid hand-typing hundreds of rating
entries — the seed is fixed so the demo dataset is stable across restarts.
"""
import random

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
        Teacher(id=7, name="Prof. Iyer"),
        Teacher(id=8, name="Dr. Bhatt"),
        Teacher(id=9, name="Dr. Kapoor"),
        Teacher(id=10, name="Prof. Menon"),
        Teacher(id=11, name="Dr. Pillai"),
        Teacher(id=12, name="Prof. Choudhary"),
    ]
    store.teachers = {t.id: t for t in teachers}
    by_name = {t.name: t.id for t in teachers}

    subjects = [
        Subject(code="IT301", name="Data Structures"),
        Subject(code="IT302", name="OS Concepts"),
        Subject(code="IT303", name="DBMS"),
        Subject(code="IT304", name="CN Lab"),
        Subject(code="IT305", name="Software Engineering"),
        Subject(code="IT306", name="Web Technologies"),
        Subject(code="IT307", name="Machine Learning"),
    ]
    store.subjects = {s.code: s for s in subjects}

    students = [
        Student(id=0, name="Pranav Waghmare", roll="23101C0006"),
        Student(id=1, name="Vedant Ghodekar", roll="23101C0007"),
        Student(id=2, name="Sujal Jakakure",  roll="23101A0018"),
        Student(id=3, name="Parth Mokashi",   roll="23101B0062"),
        Student(id=4, name="Ananya Deshmukh", roll="23101A0019"),
        Student(id=5, name="Rohan Kulkarni",  roll="23101A0020"),
        Student(id=6, name="Ishaan Patil",    roll="23101A0021"),
        Student(id=7, name="Sneha Kadam",     roll="23101B0063"),
        Student(id=8, name="Aditya Rane",     roll="23101B0064"),
        Student(id=9, name="Priya Shah",      roll="23101B0065"),
        Student(id=10, name="Kunal Bhosale",  roll="23101C0008"),
        Student(id=11, name="Neha Iyer",      roll="23101C0009"),
        Student(id=12, name="Rahul Gaikwad",  roll="23101C0010"),
        Student(id=13, name="Divya Naik",     roll="23101A0022"),
        Student(id=14, name="Yash Chavan",    roll="23101B0066"),
    ]
    store.students = {s.id: s for s in students}

    sections = [
        # IT301 — Data Structures
        Section(id=0, subject_code="IT301", label="A", teacher_id=by_name["Dr. Sharma"], room="L101", capacity=8,
                meetings=[Meeting("Mon", "9:00"), Meeting("Wed", "9:00")]),
        Section(id=1, subject_code="IT301", label="B", teacher_id=by_name["Prof. Mehta"], room="L102", capacity=8,
                meetings=[Meeting("Tue", "11:00")]),
        Section(id=2, subject_code="IT301", label="C", teacher_id=by_name["Dr. Sharma"], room="L103", capacity=8,
                meetings=[Meeting("Wed", "14:00")]),
        # IT302 — OS Concepts
        Section(id=3, subject_code="IT302", label="A", teacher_id=by_name["Prof. Joshi"], room="L201", capacity=8,
                meetings=[Meeting("Mon", "11:00")]),
        Section(id=4, subject_code="IT302", label="B", teacher_id=by_name["Dr. Nair"], room="L202", capacity=8,
                meetings=[Meeting("Thu", "9:00")]),
        Section(id=5, subject_code="IT302", label="C", teacher_id=by_name["Prof. Joshi"], room="L203", capacity=8,
                meetings=[Meeting("Fri", "10:00")]),
        # IT303 — DBMS
        Section(id=6, subject_code="IT303", label="A", teacher_id=by_name["Dr. Verma"], room="L301", capacity=8,
                meetings=[Meeting("Tue", "9:00"), Meeting("Thu", "11:00")]),
        Section(id=7, subject_code="IT303", label="B", teacher_id=by_name["Prof. Kulkarni"], room="L302", capacity=8,
                meetings=[Meeting("Wed", "11:00")]),
        Section(id=8, subject_code="IT303", label="C", teacher_id=by_name["Dr. Verma"], room="L303", capacity=8,
                meetings=[Meeting("Sat", "9:00")]),
        # IT304 — CN Lab (deliberately single-faculty: both sections are
        # taught by the same teacher, so there's nothing to rank — see
        # api/catalog.py's faculty-by-subject endpoint).
        Section(id=9, subject_code="IT304", label="A", teacher_id=by_name["Prof. Rao"], room="Lab1", capacity=8,
                meetings=[Meeting("Thu", "14:00")]),
        Section(id=10, subject_code="IT304", label="B", teacher_id=by_name["Prof. Rao"], room="Lab1", capacity=8,
                meetings=[Meeting("Fri", "14:00")]),
        # IT305 — Software Engineering
        Section(id=11, subject_code="IT305", label="A", teacher_id=by_name["Prof. Iyer"], room="L401", capacity=8,
                meetings=[Meeting("Mon", "14:00")]),
        Section(id=12, subject_code="IT305", label="B", teacher_id=by_name["Dr. Bhatt"], room="L402", capacity=8,
                meetings=[Meeting("Wed", "16:00")]),
        Section(id=13, subject_code="IT305", label="C", teacher_id=by_name["Prof. Iyer"], room="L403", capacity=8,
                meetings=[Meeting("Fri", "9:00")]),
        # IT306 — Web Technologies
        Section(id=14, subject_code="IT306", label="A", teacher_id=by_name["Dr. Kapoor"], room="Lab2", capacity=8,
                meetings=[Meeting("Tue", "14:00")]),
        Section(id=15, subject_code="IT306", label="B", teacher_id=by_name["Prof. Menon"], room="Lab2", capacity=8,
                meetings=[Meeting("Thu", "16:00")]),
        Section(id=16, subject_code="IT306", label="C", teacher_id=by_name["Dr. Kapoor"], room="Lab2", capacity=8,
                meetings=[Meeting("Sat", "11:00")]),
        # IT307 — Machine Learning (Sec A intentionally overlaps IT303 Sec B
        # on Wed 11:00 — a genuine scheduling conflict for the solver to
        # route around, since both subjects have other sections available).
        Section(id=17, subject_code="IT307", label="A", teacher_id=by_name["Dr. Pillai"], room="L501", capacity=8,
                meetings=[Meeting("Mon", "16:00"), Meeting("Wed", "11:00")]),
        Section(id=18, subject_code="IT307", label="B", teacher_id=by_name["Prof. Choudhary"], room="L502", capacity=8,
                meetings=[Meeting("Tue", "16:00")]),
        Section(id=19, subject_code="IT307", label="C", teacher_id=by_name["Dr. Pillai"], room="L503", capacity=8,
                meetings=[Meeting("Sat", "14:00")]),
    ]
    store.sections = {s.id: s for s in sections}

    store.time_slots = [
        TimeSlot(key=f"{d}|{t}", day=d, time=t, label=f"{d} {t}")
        for d in DAYS for t in PERIODS
    ]

    # ── Time-slot preferences ────────────────────────────────────────────
    # Students 0-3 keep their original hand-authored ratings byte-for-byte
    # (no change to previously-observed solver behavior for them), extended
    # only with ratings for the newly-added subjects' time slots.
    store.student_ts_prefs = {
        0: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
            "Wed|11:00": 2, "Wed|14:00": 3, "Thu|9:00": 1, "Thu|14:00": 2,
            "Fri|10:00": 2, "Fri|14:00": 1,
            "Sat|9:00": 2, "Mon|14:00": 1, "Wed|16:00": 2, "Fri|9:00": 1,
            "Tue|14:00": 3, "Thu|16:00": 1, "Sat|11:00": 2, "Mon|16:00": 1,
            "Tue|16:00": 2, "Sat|14:00": 1},
        1: {"Mon|9:00": 3, "Mon|11:00": 1, "Tue|9:00": 2, "Tue|11:00": 1,
            "Wed|11:00": 1, "Wed|14:00": 2, "Thu|9:00": 2, "Thu|14:00": 1,
            "Fri|10:00": 3, "Fri|14:00": 2,
            "Sat|9:00": 1, "Mon|14:00": 2, "Wed|16:00": 1, "Fri|9:00": 3,
            "Tue|14:00": 1, "Thu|16:00": 2, "Sat|11:00": 1, "Mon|16:00": 3,
            "Tue|16:00": 1, "Sat|14:00": 2},
        2: {"Mon|9:00": 2, "Mon|11:00": 2, "Tue|9:00": 3, "Tue|11:00": 4,
            "Wed|11:00": 1, "Wed|14:00": 1, "Thu|9:00": 1, "Thu|14:00": 3,
            "Fri|10:00": 2, "Fri|14:00": 1,
            "Sat|9:00": 3, "Mon|14:00": 1, "Wed|16:00": 2, "Fri|9:00": 1,
            "Tue|14:00": 2, "Thu|16:00": 1, "Sat|11:00": 3, "Mon|16:00": 2,
            "Tue|16:00": 1, "Sat|14:00": 1},
        3: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
            "Wed|11:00": 3, "Wed|14:00": 2, "Thu|9:00": 3, "Thu|14:00": 2,
            "Fri|10:00": 1, "Fri|14:00": 1,
            "Sat|9:00": 1, "Mon|14:00": 3, "Wed|16:00": 1, "Fri|9:00": 2,
            "Tue|14:00": 1, "Thu|16:00": 3, "Sat|11:00": 1, "Mon|16:00": 2,
            "Tue|16:00": 1, "Sat|14:00": 2},
    }
    # Students 4-14 (new demo roster) get generated ratings — see
    # _demo_ts_prefs() below. Deliberately never generates a Blocked (4)
    # rating, since student 2 above already demonstrates blocking, and
    # every subject has sections spread across enough distinct times that
    # a single stray block couldn't eliminate a whole subject anyway.
    for student in students[4:]:
        store.student_ts_prefs[student.id] = _demo_ts_prefs(student.id)

    # ── Faculty preferences, per subject ────────────────────────────────
    dr_sharma, prof_mehta = by_name["Dr. Sharma"], by_name["Prof. Mehta"]
    prof_joshi, dr_nair = by_name["Prof. Joshi"], by_name["Dr. Nair"]
    dr_verma, prof_kulkarni = by_name["Dr. Verma"], by_name["Prof. Kulkarni"]
    prof_iyer, dr_bhatt = by_name["Prof. Iyer"], by_name["Dr. Bhatt"]
    dr_kapoor, prof_menon = by_name["Dr. Kapoor"], by_name["Prof. Menon"]
    dr_pillai, prof_choudhary = by_name["Dr. Pillai"], by_name["Prof. Choudhary"]

    # Subjects with more than one teacher — the only ones worth ranking.
    # IT304 is intentionally excluded (single faculty, nothing to rank).
    RANKABLE_SUBJECTS = {
        "IT301": [dr_sharma, prof_mehta],
        "IT302": [prof_joshi, dr_nair],
        "IT303": [dr_verma, prof_kulkarni],
        "IT305": [prof_iyer, dr_bhatt],
        "IT306": [dr_kapoor, prof_menon],
        "IT307": [dr_pillai, prof_choudhary],
    }

    store.student_faculty_prefs = {
        0: {"IT301": {dr_sharma: 1, prof_mehta: 2},
            "IT302": {prof_joshi: 1, dr_nair: 2},
            "IT303": {dr_verma: 1, prof_kulkarni: 2},
            "IT305": {prof_iyer: 1, dr_bhatt: 2},
            "IT306": {dr_kapoor: 1, prof_menon: 2},
            "IT307": {dr_pillai: 1, prof_choudhary: 2}},
        1: {"IT301": {prof_mehta: 1, dr_sharma: 3},
            "IT302": {dr_nair: 3, prof_joshi: 1},
            "IT303": {prof_kulkarni: 1, dr_verma: 2},
            "IT305": {dr_bhatt: 1, prof_iyer: 2},
            "IT306": {prof_menon: 3, dr_kapoor: 1},
            "IT307": {prof_choudhary: 1, dr_pillai: 2}},
        2: {"IT301": {dr_sharma: 1, prof_mehta: 1},
            "IT302": {prof_joshi: 1, dr_nair: 1},
            "IT303": {dr_verma: 2, prof_kulkarni: 1},
            "IT305": {prof_iyer: 1, dr_bhatt: 1},
            "IT306": {dr_kapoor: 1, prof_menon: 1},
            "IT307": {dr_pillai: 2, prof_choudhary: 1}},
        3: {"IT301": {prof_mehta: 2, dr_sharma: 1},
            "IT302": {dr_nair: 1, prof_joshi: 2},
            "IT303": {prof_kulkarni: 3, dr_verma: 1},
            "IT305": {dr_bhatt: 2, prof_iyer: 1},
            "IT306": {prof_menon: 1, dr_kapoor: 2},
            "IT307": {prof_choudhary: 3, dr_pillai: 1}},
        # IT304 intentionally omitted for every student: both its sections
        # are taught by the same teacher (Prof. Rao), so there is nothing
        # to rank — see api/catalog.py's faculty-by-subject endpoint.
    }
    for student in students[4:]:
        store.student_faculty_prefs[student.id] = _demo_faculty_prefs(student.id, RANKABLE_SUBJECTS)

    return store


def _demo_ts_prefs(student_id: int) -> dict:
    """Deterministic, demo-only time-slot ratings for students 4+ (0-3 keep
    their original hand-authored ratings above). Seeded by student id so
    the dataset — and therefore the demo — looks identical on every
    restart, while still varying across students. Leans toward
    Preferred/Tolerable with occasional Disliked; never generates Blocked
    (see the comment where this is called for why that's safe here)."""
    rng = random.Random(7000 + student_id)
    prefs = {}
    for day in DAYS:
        for period in PERIODS:
            roll = rng.random()
            if roll < 0.35:
                prefs[f"{day}|{period}"] = 1
            elif roll < 0.65:
                prefs[f"{day}|{period}"] = 2
            elif roll < 0.85:
                prefs[f"{day}|{period}"] = 3
            # else: leave unrated -> defaults to indifferent (see solver/helpers.py)
    return prefs


def _demo_faculty_prefs(student_id: int, rankable_subjects: dict) -> dict:
    """Deterministic, demo-only faculty ranking for students 4+, covering
    only subjects with more than one teacher (nothing to rank otherwise).
    Always keeps at least one teacher per subject rated Preferred/Tolerable
    for a given student, so nobody can ever end up disliking every teacher
    of a subject and being stuck with an unavoidable faculty penalty."""
    rng = random.Random(9000 + student_id)
    prefs = {}
    for code, teacher_ids in rankable_subjects.items():
        shuffled = list(teacher_ids)
        rng.shuffle(shuffled)
        ranking = {shuffled[0]: rng.choice([1, 1, 2])}
        for tid in shuffled[1:]:
            ranking[tid] = rng.choice([1, 2, 3])
        prefs[code] = ranking
    return prefs

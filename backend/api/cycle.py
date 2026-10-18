"""Admin API for department-level timetable cycle management.

Routes:
  GET  /admin/cycle
      Returns current cycle status: active semesters derived from catalog,
      subject and student counts per semester, teacher counts, choice tag
      configs, student lock-in progress, and current generation run info.

  PUT  /admin/cycle/choice-tags
      Configure which subject tags are choice-based (electives) for the cycle.

  POST /admin/cycle/initialize
      Auto-creates or refreshes the generation run covering all active
      semesters in the subject catalog.
"""
import csv
import io
import random
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.enums import RunStatus
from domain.models import StudentChoiceSelection

router = APIRouter(
    prefix="/admin/cycle",
    dependencies=[Depends(require_admin)],
)


class ChoiceTagItem(BaseModel):
    tag: str
    is_choice_based: bool = True


def _get_cycle_status_dict(store: InMemoryStore) -> Dict[str, Any]:
    subjects = list(store.subjects.values())
    students = list(store.students.values())

    active_semesters = sorted({s.semester for s in subjects})
    subjects_per_sem = {}
    for sem in active_semesters:
        subjects_per_sem[sem] = len([s for s in subjects if s.semester == sem])

    students_per_sem = {}
    for s in students:
        students_per_sem[s.semester] = students_per_sem.get(s.semester, 0) + 1

    choice_configs = store.get_cycle_choice_configs()
    all_tags = store.list_subject_tags()
    choice_groups = store.get_choice_groups()

    tags_detail = []
    for tag in all_tags:
        subtags = choice_groups.get(tag, [])
        default_is_choice = bool(subtags and tag.upper() != "CORE")
        tags_detail.append({
            "tag": tag,
            "is_choice_based": choice_configs.get(tag, default_is_choice),
            "subtags": subtags,
        })

    lock_in_complete = 0
    students_lock_in = []
    for s in students:
        is_complete = store.has_complete_lock_in(s.roll_number)
        if is_complete:
            lock_in_complete += 1
        locked = store.get_lock_in_for_student(s.roll_number)
        sem_subjects = store.list_subjects(semester=s.semester)
        cb_tags = store.get_choice_based_tags_for_semester(s.semester)
        applicable_tags = sorted(list({sub.subject_tag for sub in sem_subjects if sub.subject_tag in cb_tags}))
        missing_tags = [t for t in applicable_tags if not locked.get(t)]
        students_lock_in.append({
            "roll_number": s.roll_number,
            "name": s.name,
            "semester": s.semester,
            "is_complete": is_complete,
            "locked_in": locked,
            "applicable_tags": applicable_tags,
            "missing_tags": missing_tags,
        })

    # Summary of semesters that have choice-based electives
    elective_semesters = []
    for sem in active_semesters:
        cb_tags = store.get_choice_based_tags_for_semester(sem)
        sem_subs = store.list_subjects(semester=sem)
        tags_info = []
        for tag in sorted(cb_tags):
            subtags = sorted({subtag for s in sem_subs if s.subject_tag == tag for subtag in s.supported_subtags})
            if subtags:
                tags_info.append({"tag": tag, "subtags": subtags})
        if tags_info:
            sem_stus = [s for s in students if s.semester == sem]
            complete_stus = [s for s in sem_stus if store.has_complete_lock_in(s.roll_number)]
            elective_semesters.append({
                "semester": sem,
                "tags": tags_info,
                "student_count": len(sem_stus),
                "allocated_count": len(complete_stus),
                "is_complete": len(sem_stus) > 0 and len(complete_stus) == len(sem_stus),
            })

    # Find the current (active or latest) generation run
    latest_run = None
    from domain.saved_runs import ensure_active_run_loaded
    ensure_active_run_loaded(store)
    if store.runs:
        active_id = getattr(store, "active_run_id", None)
        if active_id is not None and active_id in store.runs:
            latest_run_obj = store.runs[active_id]
        else:
            latest_run_obj = max(store.runs.values(), key=lambda r: r.id)
        latest_run = {
            "id": latest_run_obj.id,
            "semesters": latest_run_obj.semesters,
            "semester": latest_run_obj.semester,
            "status": latest_run_obj.status.value,
        }

    return {
        "active_semesters": active_semesters,
        "subjects_per_semester": subjects_per_sem,
        "students_per_semester": students_per_sem,
        "teachers_count": len(store.teachers),
        "choice_tags": tags_detail,
        "tags_detail": tags_detail,
        "elective_semesters": elective_semesters,
        "lock_in_complete_count": lock_in_complete,
        "lock_in_total_students": len(students),
        "students_lock_in": students_lock_in,
        "current_run": latest_run,
    }


@router.get("")
def get_cycle_status(store: InMemoryStore = Depends(get_store)):
    return _get_cycle_status_dict(store)



@router.put("/choice-tags")
def update_cycle_choice_tags(
    payload: Any = Body(...),
    store: InMemoryStore = Depends(get_store),
):
    existing_tags = set(store.list_subject_tags())
    new_configs: Dict[str, bool] = {}

    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if "configs" in payload:
            cfg = payload["configs"]
            if isinstance(cfg, list):
                items = cfg
            elif isinstance(cfg, dict):
                for k, v in cfg.items():
                    items.append({"tag": k, "is_choice_based": bool(v)})
        else:
            for k, v in payload.items():
                items.append({"tag": k, "is_choice_based": bool(v)})

    for item in items:
        if isinstance(item, dict):
            tag = item.get("tag")
            is_cb = item.get("is_choice_based", True)
        else:
            tag = getattr(item, "tag", None)
            is_cb = getattr(item, "is_choice_based", True)

        if not tag:
            continue
        if tag not in existing_tags:
            raise HTTPException(
                status_code=400,
                detail=f"Tag '{tag}' does not exist in the subject catalog.",
            )
        new_configs[tag] = bool(is_cb)

    store.set_cycle_choice_configs(new_configs)
    return _get_cycle_status_dict(store)


@router.post("/initialize")
def initialize_cycle(store: InMemoryStore = Depends(get_store)):
    """Initialize or update a generation run covering all active semesters."""
    active_semesters = sorted({s.semester for s in store.subjects.values()})
    if not active_semesters:
        raise HTTPException(
            status_code=400,
            detail="No subjects found in catalog. Upload subjects before initializing a cycle.",
        )

    # If there is an existing DRAFT run, reuse and update it
    draft_run = next((r for r in store.runs.values() if r.status == RunStatus.DRAFT), None)
    if draft_run is not None:
        draft_run.semesters = active_semesters
        run = draft_run
    else:
        run = store.create_run(semesters=active_semesters)

    run_dict = {
        "id": run.id,
        "semesters": run.semesters,
        "semester": run.semester,
        "status": run.status.value,
    }

    return {
        "run_id": run.id,
        "semesters": run.semesters,
        "semester": run.semester,
        "status": run.status.value,
        "current_run": run_dict,
    }


@router.post("/auto-lock-in")
def auto_lock_in_pending_students(store: InMemoryStore = Depends(get_store)):
    """Auto-assign a random available elective choice per tag to pending students."""
    cb_tags = store.get_choice_based_tags()
    subjects = list(store.subjects.values())
    count = 0
    for s in store.students.values():
        if store.has_complete_lock_in(s.roll_number):
            continue
        sem_subs = [sub for sub in subjects if sub.semester == s.semester and sub.subject_tag in cb_tags]
        tag_subtags = {}
        for sub in sem_subs:
            for subtag in sub.supported_subtags:
                tag_subtags.setdefault(sub.subject_tag, set()).add(subtag)

        choices = {}
        for tag, subtags in tag_subtags.items():
            if subtags:
                choices[tag] = random.choice(sorted(subtags))

        if choices:
            selections = [
                StudentChoiceSelection(roll_number=s.roll_number, tag=tag, subtag=subtag)
                for tag, subtag in choices.items()
            ]
            store.set_student_choice_selections(s.roll_number, selections)
            count += 1

    return {
        "status": "completed",
        "auto_locked_count": count,
        "cycle": _get_cycle_status_dict(store),
    }


@router.get("/elective-template/{semester}")
def download_elective_template(
    semester: int,
    store: InMemoryStore = Depends(get_store),
):
    """Download dynamically generated CSV template for student elective allocations in a semester."""
    cb_tags = store.get_choice_based_tags_for_semester(semester)
    sem_subs = store.list_subjects(semester=semester)
    tag_subtags: Dict[str, List[str]] = {}
    for tag in sorted(cb_tags):
        subtags = sorted({subtag for s in sem_subs if s.subject_tag == tag for subtag in s.supported_subtags})
        if subtags:
            tag_subtags[tag] = subtags

    if not tag_subtags:
        raise HTTPException(
            status_code=400,
            detail=f"No choice-based elective tags with subtags found for Semester {semester}.",
        )

    students = [s for s in store.list_students(semester=semester)]
    students.sort(key=lambda s: s.roll_number)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header comments showing allowed options for each column
    options_summary = " | ".join([f"{tag} options: {', '.join(subtags)}" for tag, subtags in tag_subtags.items()])
    output.write(f"# Semester {semester} Elective Allocations Template\n")
    output.write(f"# Allowed options: {options_summary}\n")

    tags_list = list(tag_subtags.keys())
    header = ["roll_number", "student_name"] + tags_list
    writer.writerow(header)

    for s in students:
        locked = store.get_lock_in_for_student(s.roll_number)
        row = [s.roll_number, s.name] + [locked.get(tag, "") for tag in tags_list]
        writer.writerow(row)

    csv_data = output.getvalue()
    filename = f"semester_{semester}_elective_allocations.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-elective-allocations")
async def import_elective_allocations(
    file: UploadFile = File(...),
    semester: Optional[int] = Form(None),
    store: InMemoryStore = Depends(get_store),
):
    """Import student elective allocations from CSV.

    Expected CSV columns: roll_number (or roll_no), and one column per elective tag (e.g. MDM, PE).
    Optionally accepts student_name / name (ignored, for reference).
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .csv file.")

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = contents.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode CSV file. Please upload UTF-8 encoded text.")

    # Skip lines starting with #
    lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
    if not lines:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV header row missing.")

    # Normalize fieldnames
    raw_fieldnames = [f.strip() for f in reader.fieldnames if f]
    field_map = {f.lower(): f for f in raw_fieldnames}

    roll_col = None
    for cand in ("roll_number", "roll_no", "rollno", "roll"):
        if cand in field_map:
            roll_col = field_map[cand]
            break

    if not roll_col:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain a 'roll_number' (or 'roll_no') column.",
        )

    # Discover which columns correspond to subject tags
    all_known_tags = {tag.upper(): tag for tag in store.list_subject_tags()}
    col_to_tag: Dict[str, str] = {}
    for col in raw_fieldnames:
        if col == roll_col or col.lower() in ("student_name", "name", "semester"):
            continue
        cleaned_col = col.strip()
        tag_key = cleaned_col.split("_")[0].upper()
        if tag_key in all_known_tags:
            col_to_tag[col] = all_known_tags[tag_key]

    if not col_to_tag:
        raise HTTPException(
            status_code=400,
            detail=f"No elective tag columns recognized in CSV headers: {raw_fieldnames}. Expected tag names like {list(all_known_tags.values())}.",
        )

    # Pre-fetch subject subtags per semester and tag
    active_sems = {s.semester for s in store.subjects.values()}
    choice_groups_by_sem: Dict[int, Dict[str, Set[str]]] = {}
    for sem in active_sems:
        choice_groups_by_sem[sem] = {}
        for sub in store.list_subjects(semester=sem):
            if sub.subject_tag:
                choice_groups_by_sem[sem].setdefault(sub.subject_tag, set()).update(sub.supported_subtags)

    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV contains header but no data rows.")

    errors = []
    allocations_to_apply = []

    for row_idx, row in enumerate(rows, start=2):
        roll = row.get(roll_col, "").strip()
        if not roll:
            continue

        student = store.get_student(roll)
        if not student:
            errors.append({
                "row": row_idx,
                "roll_number": roll,
                "error": f"Student with roll number '{roll}' does not exist in student roster.",
            })
            continue

        if semester is not None and student.semester != semester:
            errors.append({
                "row": row_idx,
                "roll_number": roll,
                "error": f"Student '{roll}' is in Semester {student.semester}, but uploaded file is for Semester {semester}.",
            })
            continue

        sem_tags = choice_groups_by_sem.get(student.semester, {})
        student_choices: Dict[str, str] = {}

        for col, tag in col_to_tag.items():
            val = row.get(col, "").strip()
            if not val:
                continue

            valid_subtags = sem_tags.get(tag, set())
            matched_subtag = next((st for st in valid_subtags if st.lower() == val.lower()), None)
            if not matched_subtag:
                allowed_str = ", ".join(sorted(valid_subtags)) if valid_subtags else "none"
                errors.append({
                    "row": row_idx,
                    "roll_number": roll,
                    "error": f"Invalid subtag '{val}' for tag '{tag}' in Semester {student.semester}. Allowed: {allowed_str}.",
                })
            else:
                student_choices[tag] = matched_subtag

        if student_choices:
            allocations_to_apply.append((roll, student_choices))

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": f"Found {len(errors)} error(s) in CSV", "errors": errors},
        )

    # Apply valid allocations
    updated_count = 0
    for roll, choices in allocations_to_apply:
        old_lock_in = store.get_lock_in_for_student(roll)
        if old_lock_in != choices:
            store.student_time_preferences.pop(roll, None)
            store.student_faculty_preferences.pop(roll, None)

        merged = dict(old_lock_in)
        merged.update(choices)
        selections = [
            StudentChoiceSelection(roll_number=roll, tag=tag, subtag=subtag)
            for tag, subtag in merged.items()
        ]
        store.set_student_choice_selections(roll, selections)
        updated_count += 1

    return {
        "status": "imported",
        "updated_count": updated_count,
        "cycle": _get_cycle_status_dict(store),
    }


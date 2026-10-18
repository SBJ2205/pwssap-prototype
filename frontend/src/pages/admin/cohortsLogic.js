// Pure helpers for the Classes & Batches page: no React, no network.
//
// A "class" here is the editable shape sent to POST /admin/cohorts/save:
//   { class_id, class_name, track, track_tag, student_rolls: [...], lab_batch_count }
// Divisions of one track (or of the single "ALL" pool) form a "group". Students may
// only move between divisions of the same group, because each division must stay
// inside one elective track.

export const MIN_BATCHES = 2;
export const MAX_BATCHES = 6;

export const groupOf = (cls) => cls.track || "ALL";

export function balancedChunks(items, parts) {
  const n = Math.max(1, parts);
  const base = Math.floor(items.length / n);
  const extra = items.length % n;
  const chunks = [];
  let start = 0;
  for (let i = 0; i < n; i++) {
    const size = base + (i < extra ? 1 : 0);
    chunks.push(items.slice(start, start + size));
    start += size;
  }
  return chunks;
}

// Sizes of the lab batches the server will create for a division.
export function batchSizes(studentCount, batchCount) {
  return balancedChunks(new Array(studentCount).fill(0), batchCount).map((c) => c.length);
}

export function letterFor(index) {
  let n = index;
  let letters = "";
  for (;;) {
    letters = String.fromCharCode(65 + (n % 26)) + letters;
    n = Math.floor(n / 26) - 1;
    if (n < 0) return letters;
  }
}

function classLetter(classId) {
  return classId.replace(/^div[-_ ]/i, "").trim();
}

// Batch ids the server will create for a division, e.g. Div-A x3 -> A1, A2, A3.
export function batchLabels(classId, batchCount) {
  const letter = classLetter(classId) || "?";
  return Array.from({ length: Math.max(0, Number(batchCount) || 0) }, (_, i) => `${letter}${i + 1}`);
}

export function nextClassId(classes) {
  const used = new Set(classes.map((c) => classLetter(c.class_id).toUpperCase()));
  for (let i = 0; i < 702; i++) {
    const letter = letterFor(i);
    if (!used.has(letter)) return `Div-${letter}`;
  }
  return `Div-${classes.length + 1}`;
}

// Re-split every student of one group evenly (contiguous by roll) across its divisions.
export function rebalanceGroup(classes, group) {
  const idxs = classes.map((c, i) => (groupOf(c) === group ? i : -1)).filter((i) => i >= 0);
  if (idxs.length === 0) return classes;
  const rolls = idxs.flatMap((i) => classes[i].student_rolls).sort();
  const chunks = balancedChunks(rolls, idxs.length);
  const next = classes.slice();
  idxs.forEach((classIdx, k) => {
    next[classIdx] = { ...classes[classIdx], student_rolls: chunks[k] };
  });
  return next;
}

// Add a division to a group (placed right after the group's last division) and rebalance the group.
export function addDivision(classes, group, trackTag) {
  const id = nextClassId(classes);
  const letter = classLetter(id);
  const track = group === "ALL" ? null : group;
  const fresh = {
    class_id: id,
    class_name: `Division ${letter}` + (track ? ` (${track})` : ""),
    track,
    track_tag: trackTag || null,
    student_rolls: [],
    lab_batch_count: 3,
  };
  let insertAt = classes.length;
  classes.forEach((c, i) => {
    if (groupOf(c) === group) insertAt = i + 1;
  });
  const next = [...classes.slice(0, insertAt), fresh, ...classes.slice(insertAt)];
  return rebalanceGroup(next, group);
}

// Remove a division; its students are redistributed over the rest of its group.
// Returns { classes, error }.
export function removeDivision(classes, idx) {
  const target = classes[idx];
  const group = groupOf(target);
  const siblings = classes.filter((c, i) => i !== idx && groupOf(c) === group);
  if (siblings.length === 0 && target.student_rolls.length > 0) {
    return { classes, error: `${target.class_id} is the only division of its group; it still has students.` };
  }
  const without = classes.filter((_, i) => i !== idx);
  const keeper = without.findIndex((c) => groupOf(c) === group);
  if (keeper >= 0) {
    without[keeper] = {
      ...without[keeper],
      student_rolls: [...without[keeper].student_rolls, ...target.student_rolls],
    };
  }
  return { classes: rebalanceGroup(without, group), error: null };
}

// Move students to another division of the same group. Returns { classes, error }.
export function moveStudents(classes, rolls, targetIdx) {
  const target = classes[targetIdx];
  if (!target || rolls.length === 0) return { classes, error: null };
  const moving = new Set(rolls);
  for (let i = 0; i < classes.length; i++) {
    const holdsMoving = classes[i].student_rolls.some((r) => moving.has(r));
    if (holdsMoving && groupOf(classes[i]) !== groupOf(target)) {
      return {
        classes,
        error: `Students of track ${groupOf(classes[i])} cannot join ${target.class_id} (track ${groupOf(target)}).`,
      };
    }
  }
  const next = classes.map((c, i) => {
    if (i === targetIdx) {
      const kept = c.student_rolls.filter((r) => !moving.has(r));
      return { ...c, student_rolls: [...kept, ...rolls.filter((r) => !c.student_rolls.includes(r))].sort() };
    }
    return { ...c, student_rolls: c.student_rolls.filter((r) => !moving.has(r)) };
  });
  return { classes: next, error: null };
}

// Problems that would make the server reject the setup (mirrors the backend rules).
export function localProblems(classes, totalStudents) {
  const problems = [];
  const placed = classes.reduce((sum, c) => sum + c.student_rolls.length, 0);
  if (placed !== totalStudents) problems.push(`${totalStudents - placed} student(s) are not placed in a division.`);
  classes.forEach((c) => {
    if (c.student_rolls.length === 0) problems.push(`${c.class_id} has no students.`);
    const batches = Number(c.lab_batch_count);
    if (!(batches >= MIN_BATCHES && batches <= MAX_BATCHES)) {
      problems.push(`${c.class_id}: lab batches must be ${MIN_BATCHES}-${MAX_BATCHES}.`);
    } else if (batches > c.student_rolls.length) {
      problems.push(`${c.class_id} has fewer students than batches.`);
    }
  });
  const ids = classes.map((c) => c.class_id.trim().toLowerCase());
  if (new Set(ids).size !== ids.length) problems.push("Division ids must be unique.");
  return problems;
}

export const toSavePayload = (semester, classes) => ({
  semester,
  classes: classes.map((c) => ({
    class_id: c.class_id,
    class_name: c.class_name,
    student_rolls: c.student_rolls,
    lab_batch_count: Number(c.lab_batch_count),
  })),
});

export const sameSetup = (a, b) =>
  JSON.stringify(toSavePayload(0, a)) === JSON.stringify(toSavePayload(0, b));

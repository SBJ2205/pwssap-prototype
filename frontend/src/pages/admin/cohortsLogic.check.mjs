// Run with: node src/pages/admin/cohortsLogic.check.mjs
import assert from "node:assert/strict";
import {
  addDivision, balancedChunks, batchSizes, localProblems, moveStudents,
  nextClassId, rebalanceGroup, removeDivision, sameSetup, toSavePayload,
} from "./cohortsLogic.js";

const rolls = (n, prefix = "R") => Array.from({ length: n }, (_, i) => `${prefix}${String(i).padStart(3, "0")}`);
const cls = (id, rs, track = null, batches = 3) => ({
  class_id: id, class_name: id, track, track_tag: track ? "PE" : null, student_rolls: rs, lab_batch_count: batches,
});

// balanced split never produces an empty batch and sizes differ by at most one
assert.deepEqual(batchSizes(5, 4), [2, 1, 1, 1]);
assert.deepEqual(batchSizes(61, 4), [16, 15, 15, 15]);
assert.deepEqual(balancedChunks([1, 2, 3, 4, 5], 2), [[1, 2, 3], [4, 5]]);

// adding a division rebalances its group, leaves other groups alone, and keeps groups contiguous
let classes = [cls("Div-A", rolls(62, "A"), "AIML"), cls("Div-B", rolls(50, "C"), "CSEC")];
classes = addDivision(classes, "AIML", "PE");
assert.deepEqual(classes.map((c) => c.class_id), ["Div-A", "Div-C", "Div-B"]);
assert.deepEqual(classes.map((c) => c.student_rolls.length), [31, 31, 50]);
assert.equal(classes.flatMap((c) => c.student_rolls).length, 112);
assert.equal(new Set(classes.flatMap((c) => c.student_rolls)).size, 112);

// removing returns students to the siblings
let r = removeDivision(classes, 1);
assert.equal(r.error, null);
assert.deepEqual(r.classes.map((c) => c.student_rolls.length), [62, 50]);
// cannot remove the only division of a group while it has students
assert.ok(removeDivision(r.classes, 1).error);

// moving students: same group only
r = moveStudents(classes, classes[0].student_rolls.slice(0, 3), 1);
assert.equal(r.error, null);
assert.deepEqual(r.classes.map((c) => c.student_rolls.length), [28, 34, 50]);
r = moveStudents(classes, classes[0].student_rolls.slice(0, 1), 2);
assert.match(r.error, /cannot join/);

// local problems mirror server rules
assert.deepEqual(localProblems(classes, 112), []);
assert.ok(localProblems(classes, 113)[0].includes("not placed"));
assert.ok(localProblems([cls("Div-A", [], null, 3)], 0).some((p) => p.includes("no students")));
assert.ok(localProblems([cls("Div-A", rolls(10), null, 7)], 10).some((p) => p.includes("2-6")));
assert.ok(localProblems([cls("Div-A", rolls(10)), cls("div-a", rolls(5, "Z"))], 15).some((p) => p.includes("unique")));

assert.equal(nextClassId([cls("Div-A", []), cls("Div-B", [])]), "Div-C");
assert.equal(rebalanceGroup([cls("Div-A", rolls(5)), cls("Div-B", [])], "ALL").map((c) => c.student_rolls.length).join(), "3,2");
assert.equal(sameSetup(classes, classes.map((c) => ({ ...c }))), true);
assert.equal(toSavePayload(6, classes).classes[0].lab_batch_count, 3);
console.log("cohortsLogic: all checks passed");

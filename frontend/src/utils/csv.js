// CSV utilities: client-side parsing for preview, templates, and browser file download.

export function downloadCsv(filename, content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// Simple RFC-compliant CSV parser for client-side preview.
export function parseCsvText(text, maxRows = 20) {
  if (!text || !text.trim()) return { header: [], rows: [] };
  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 0) return { header: [], rows: [] };

  function parseLine(line) {
    const result = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"' && (i === 0 || line[i - 1] !== "\\")) {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        result.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  }

  const header = parseLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length && rows.length < maxRows; i++) {
    if (!lines[i].trim()) continue;
    rows.push(parseLine(lines[i]));
  }
  return { header, rows, totalRows: lines.length - 1 };
}

// ── Templates ────────────────────────────────────────────────────────────

export const SUBJECT_CSV_TEMPLATE = `subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity,slot_structure
IT301,Data Structures,CORE,3,theory,3,60,
IT302,Database Management Systems,CORE,3,theory,3,60,
IT303,Data Structures Lab,CORE,3,lab,2,20,
IT304,Database Systems Lab,CORE,3,lab,2,20,
IT305,Object Oriented Programming,CORE,3,theory,3,60,
IT306,OOP Lab,CORE,3,lab,2,20,
IT307,Web Technologies,PE1,3,theory,3,30,
IT308,Mobile Computing,PE1,3,theory,3,30,
IT309,Cloud Foundations,MDM,3,theory,3,30,
IT310,Cyber Security Intro,MDM,3,theory,3,30,
`;

export const TEACHER_CSV_TEMPLATE = `teacher_id,teacher_name,subject_1,subject_2,subject_3,subject_4
T001,Dr. A. Sharma,IT301,IT302,IT303,IT304
T002,Prof. B. Verma,IT301,IT305,IT306,IT307
T003,Dr. C. Iyer,IT302,IT305,IT308,IT309
T004,Prof. D. Kulkarni,IT303,IT304,IT306,IT310
T005,Dr. E. Deshmukh,IT307,IT308,IT309,IT310
`;

export function generateStudentCsvTemplate(activeRun) {
  const activeConfigs = (activeRun?.choice_tag_configs || []).filter(c => c.is_choice_based);
  const choiceCols = activeConfigs.map((_, idx) => `choice_${idx + 1}`);
  const header = ["roll_number", "name", "semester", ...choiceCols].join(",");

  const semester = activeRun?.semester || 3;
  if (activeConfigs.length === 0) {
    return `${header}
23101C0001,Aarav Patil,${semester}
23101C0002,Diya Shah,${semester}
23101C0003,Rohan Joshi,${semester}
`;
  }

  // Example choice values using the actual numeric values
  const val1 = activeConfigs[0]?.numeric_value || 1;
  const val2 = activeConfigs[1]?.numeric_value || (val1 === 1 ? 2 : 1);
  const valOther = activeConfigs.map(c => c.numeric_value);

  const row1Choices = activeConfigs.map(c => c.numeric_value).join(",");
  const row2Choices = activeConfigs.slice().reverse().map(c => c.numeric_value).join(",");
  const row3Choices = [val2, val1, ...valOther.slice(2)].join(",");

  return `${header}
23101C0001,Aarav Patil,${semester},${row1Choices}
23101C0002,Diya Shah,${semester},${row2Choices}
23101C0003,Rohan Joshi,${semester},${row3Choices}
`;
}

# Timetable Coordinator Guide — PWSSAP (Traditional Mode)

Welcome! This system generates conflict-free college timetables using constraint-based optimization (Google OR-Tools).

Even though the system supports advanced student time-slot preference weighting, you can use **Traditional Division & Batch Mode**, which creates fixed class divisions (Div A, Div B, etc.) and laboratory batches (B1, B2, B3) just like standard university schedules.

---

## 🚀 1. How to Start the Application

1. Open the project folder on your Windows computer.
2. **Double-click `Run_PWSSAP.bat`**.
   *(Optional: You can also double-click `Create_Desktop_Shortcut.bat` once to place a handy shortcut icon directly on your Desktop!)*
3. A command window will open, and within a few seconds, the **PWSSAP Timetable Management System** will automatically open in a dedicated application window (or your default web browser) at:
   `http://localhost:8000`

---

## 🔑 2. Logging In

1. On the welcome screen, enter the word:
   **`admin`**
2. Click **Enter / Log In**. You are now logged in with full Timetable Coordinator access.

---

## 📋 3. Step-by-Step Workflow for Traditional Mode

### Step 1: Set Up Department Data (Catalog)
In the left sidebar, you have options to manage your departmental data:
- **Teachers**: Add or upload teachers (`teachers.csv`). You can also specify which subjects each teacher is qualified to teach.
- **Teacher Availability**: Click any time slots on the grid to mark when specific faculty (e.g., HOD, Deans, senior professors) are unavailable or busy with administrative duties. The solver guarantees they will never be scheduled in blocked slots.
- **Subjects**: Add or upload semester courses (`subjects.csv`). Specify whether each subject is a Theory lecture, Laboratory, or Elective, along with its weekly hours.
- **Students**: Upload student roster lists (`students.csv`).

> 💡 *Tip: If you want to try out the system immediately with realistic sample college data, ready-to-use CSV files are located in the `demo_run/` folder.*

---

### Step 2: Configure Classes & Batches (Traditional Mode)
1. In the sidebar, click **"Classes & Batches (Traditional)"** (or Cohorts).
2. The system automatically suggests class divisions (e.g., Semester 4: Div-A, Div-B, Div-C, Div-D) and laboratory batches based on student counts and classroom capacity.
3. You can review the roster for each division, reassign students between divisions/batches if needed, or adjust the number of lab batches (2 to 4 batches).
4. Click the green button: **"Generate Traditional Sections"**.
   - This creates fixed theory sections per division and lab sections per batch.
   - It automatically pins students so their classmates stay together in the same division.

---

### Step 3: Run the Timetable Solver
1. In the sidebar, click **"Solver"**.
2. Notice the indicator: **`🏛 Active Mode: Traditional Cohort`**.
3. Select your time limit (e.g., 60 to 120 seconds).
4. Click **"Run Solver"**.
5. The Google OR-Tools optimization engine will construct the master schedule, ensuring:
   - ✅ **Zero teacher clashes** (no teacher is ever double-booked).
   - ✅ **Zero student clashes** (no division or lab batch has overlapping classes).
   - ✅ **Lab synchronization** (all lab batches for a division meet in parallel lab slots).
   - ✅ **Adherence to teacher availability and load limits**.
6. When completed, the status will show **`OPTIMAL`** or **`FEASIBLE`**.
7. Click **"Save Snapshot"** to name and archive this solved run (e.g., *"Semester 4 & 6 Final Schedule"*).

---

### Step 4: View & Validate the Timetable
- In the sidebar, click **"Timetable"**:
  - Filter by **Semester** (e.g., Semester 4, Semester 6).
  - Filter by **Division** (e.g., Div-A, Div-B) to see a clean class schedule.
  - Filter by **Faculty** to view any individual teacher's weekly schedule.
  - Print or export the schedule for distribution.
- In **"Classes & Batches"**, check the **Validation Report**:
  - The independent validator runs 8 structural checks to verify that every student has all required courses and that there are 0 hard violations.

---

## 🛑 4. How to Stop the Application

When you are done:
1. Close the application browser window.
2. In the black terminal window, press **Ctrl + C** (or simply click the **X** button in the top right corner to close the terminal).

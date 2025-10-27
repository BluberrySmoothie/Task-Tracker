import sys
import os
import tempfile
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
from PyQt5.QtWidgets import (
    QApplication, QWidget, QTabWidget, QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QMessageBox, QHBoxLayout, QComboBox, QDateEdit, QFormLayout, QFileDialog, QHeaderView,
    QVBoxLayout, QSplashScreen, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt5.QtGui import QPixmap, QScreen, QPainter
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import matplotlib.dates as mdates # Import matplotlib.dates

DB_NAME = "task_tracker.db3"

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            start_date TEXT,
            due_date TEXT,
            status TEXT,
            owner TEXT,
            priority TEXT,
            project TEXT,  -- New 'project' column
            FOREIGN KEY(owner) REFERENCES users(username),
            FOREIGN KEY(project) REFERENCES projects(project_name)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_name TEXT PRIMARY KEY
        )
    """)
    conn.commit()

    # Add 'project' column to tasks table if it doesn't exist
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN project TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise
    finally:
        conn.close()


# --- Helpers ---
def run_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(query, params)
    data = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def get_working_day_before(d):
    # Return the previous working day (skip weekends)
    offset = 1
    while True:
        candidate = d - timedelta(days=offset)
        if candidate.weekday() < 5:  # Mon-Fri are 0-4
            return candidate
        offset += 1

# --- Custom Header View for Filtering (now only handles menu) ---
class FilterHeaderView(QHeaderView):
    # Signal emitted when a filter is applied to a column
    filterRequested = pyqtSignal(int, str) # column index, filter value

    def __init__(self, orientation, table_widget, app_instance):
        super().__init__(orientation, table_widget)
        self.setSectionsClickable(True)
        self.setStretchLastSection(True)
        self.setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget = table_widget
        self.app_instance = app_instance # Store reference to TaskTrackerApp
        self.filterable_columns = ["Status", "Owner", "Priority", "Project"] # Columns to allow filtering on

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            logical_index = self.logicalIndexAt(event.pos())
            if logical_index >= 0:
                header_text = self.model().headerData(logical_index, self.orientation()).strip()
                # Check if the header text, before any (F) is added, is in filterable columns
                original_header_text = header_text.replace(' (F)', '') # Remove (F) if present
                if original_header_text in self.filterable_columns:
                    self.show_filter_menu(logical_index, original_header_text, event.globalPos())
                    return # Consume the event
        super().mousePressEvent(event)

    def show_filter_menu(self, logical_index, column_name, pos):
        menu = QMenu(self.parent())

        # Get all unique values for the column from the database
        unique_values = run_query(f"SELECT DISTINCT {column_name.replace(' ', '_').lower()} FROM tasks ORDER BY {column_name.replace(' ', '_').lower()}", fetch=True)
        unique_values = [str(val[0]) for val in unique_values if val[0] is not None]

        # Add "All" option to clear filter
        action_all = QAction("All", menu)
        action_all.triggered.connect(lambda: self.filterRequested.emit(logical_index, "All"))
        menu.addAction(action_all)
        menu.addSeparator()

        # Add unique values as actions
        for value in sorted(unique_values):
            action = QAction(value, menu)
            action.triggered.connect(lambda checked, idx=logical_index, val=value: self.filterRequested.emit(idx, val))
            menu.addAction(action)

        menu.exec_(pos)

    # paintSection override is removed, as filter indication is now done via modifying header text


# --- Main Window ---
class TaskTrackerApp(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Task Tracker V2.3")
        self.setGeometry(100, 100, 1100, 650)
        self.current_filters = {} # Dictionary to store active filters: {column_name: filter_value}
        
        # Define original header labels, in order
        self.original_header_labels = ["ID", "Title", "Desc", "Start", "Due", "Status", "Owner", "Priority", "Project"]

        self.initUI()

    def initUI(self):
        self.task_tab = QWidget()
        self.user_tab = QWidget()
        self.holiday_tab = QWidget()
        self.project_tab = QWidget()
        self.gantt_tab = QWidget()
        self.export_tab = QWidget()
        self.about_tab = QWidget()

        self.addTab(self.task_tab, "Tasks")
        self.addTab(self.user_tab, "Users")
        self.addTab(self.holiday_tab, "Holidays")
        self.addTab(self.project_tab, "Projects")
        self.addTab(self.gantt_tab, "Gantt Chart")
        self.addTab(self.export_tab, "Export")
        self.addTab(self.about_tab, "About")

        self.currentChanged.connect(self.tab_changed)

        self.init_task_tab()
        self.init_user_tab()
        self.init_holiday_tab()
        self.init_gantt_tab()
        self.init_export_tab()
        self.init_project_tab()
        self.init_about_tab()

    def tab_changed(self, index):
        tab = self.tabText(index)
        if tab == "Tasks":
            self.update_user_combobox()
            self.update_project_combobox()
            self.load_tasks() # Ensure filters are applied when returning to tasks tab
            # No need to call viewport().update() here for header, as load_tasks updates labels directly
        elif tab == "Users":
            self.load_users()
        elif tab == "Holidays":
            self.load_holidays()
        elif tab == "Projects":
            self.load_projects()
        elif tab == "Gantt Chart":
            self.update_user_filter_combobox()
            self.update_project_filter_combobox()
            # Recalculate and set the default start date each time the Gantt chart tab is shown
            self.set_gantt_default_start_date()
            self.draw_gantt()
        elif tab == "Export":
            self.update_export_user_filter_combobox()
            self.update_export_project_filter_combobox()

    # --- TASK TAB ---
    def init_task_tab(self):
        layout = QVBoxLayout()

        form = QFormLayout()
        self.title_input = QLineEdit()
        self.desc_input = QLineEdit()
        self.start_input = QDateEdit(calendarPopup=True)
        self.start_input.setDate(date.today())
        self.due_input = QDateEdit(calendarPopup=True)
        self.due_input.setDate(date.today())
        self.status_input = QComboBox()
        self.status_input.addItems(["Open", "Done"])
        self.owner_input = QComboBox()
        self.update_user_combobox()
        self.priority_input = QComboBox()
        self.priority_input.addItems(["Low", "Medium", "High"])
        self.project_input = QComboBox()
        self.update_project_combobox()

        form.addRow("Title", self.title_input)
        form.addRow("Description", self.desc_input)
        form.addRow("Start Date", self.start_input)
        form.addRow("Due Date", self.due_input)
        form.addRow("Status", self.status_input)
        form.addRow("Owner", self.owner_input)
        form.addRow("Priority", self.priority_input)
        form.addRow("Project", self.project_input)

        add_btn = QPushButton("Add Task")
        update_btn = QPushButton("Update Task")
        delete_btn = QPushButton("Delete Task")
        add_btn.clicked.connect(self.add_task)
        update_btn.clicked.connect(self.update_task)
        delete_btn.clicked.connect(self.delete_task)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(form)
        layout.addLayout(btn_layout)

        self.task_table = QTableWidget()
        self.task_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.task_table.itemSelectionChanged.connect(self.populate_task_fields)
        
        # Set custom header view for filtering
        self.header_view = FilterHeaderView(Qt.Horizontal, self.task_table, self) # Pass self (TaskTrackerApp)
        self.task_table.setHorizontalHeader(self.header_view)
        self.header_view.filterRequested.connect(self.apply_column_filter)

        layout.addWidget(self.task_table)
        self.load_tasks()

        self.task_tab.setLayout(layout)

    def apply_column_filter(self, col_index, filter_value):
        # Map column index back to column name using original header labels
        # Using self.original_header_labels to get the base column name
        column_name = self.original_header_labels[col_index]

        # Convert header name to database column name
        db_column_name_map = {
            "ID": "id",
            "Title": "title",
            "Desc": "description",
            "Start": "start_date",
            "Due": "due_date",
            "Status": "status",
            "Owner": "owner",
            "Priority": "priority",
            "Project": "project"
        }
        db_column = db_column_name_map.get(column_name, column_name.lower().replace(' ', '_'))

        if filter_value == "All":
            if db_column in self.current_filters:
                del self.current_filters[db_column]
        else:
            self.current_filters[db_column] = filter_value
        
        # Clear selected row to prevent stale data in input fields if user clicks header while a row is selected
        self.task_table.clearSelection()
        self.title_input.clear()
        self.desc_input.clear()
        self.start_input.setDate(date.today())
        self.due_input.setDate(date.today())
        self.status_input.setCurrentIndex(0)
        # Safely try to set index to 0 if owner_input has items, otherwise clear
        if self.owner_input.count() > 0:
            self.owner_input.setCurrentIndex(0)
        else:
            self.owner_input.clear() # Or handle as per desired empty state
        self.priority_input.setCurrentIndex(0)
        if self.project_input.count() > 0:
            self.project_input.setCurrentIndex(0)
        else:
            self.project_input.clear() # Or handle as per desired empty state

        self.load_tasks() # Reload tasks with new filters - this will now also update the header labels


    def load_tasks(self):
        query_parts = ["SELECT id, title, description, start_date, due_date, status, owner, priority, project FROM tasks WHERE 1=1"]
        params = []

        for col_name, filter_value in self.current_filters.items():
            query_parts.append(f" AND {col_name} = ?")
            params.append(filter_value)
        
        query = " ".join(query_parts) + " ORDER BY id DESC" # Added ordering
        data = run_query(query, params, fetch=True)

        self.task_table.setRowCount(len(data))
        self.task_table.setColumnCount(9)
        
        # Dynamically create header labels with (F) for filtered columns
        db_column_name_map = {
            "ID": "id", "Title": "title", "Desc": "description",
            "Start": "start_date", "Due": "due_date", "Status": "status",
            "Owner": "owner", "Priority": "priority", "Project": "project"
        }
        
        display_header_labels = []
        for original_label in self.original_header_labels:
            db_col_name = db_column_name_map.get(original_label, original_label.lower().replace(' ', '_'))
            if db_col_name in self.current_filters and self.current_filters[db_col_name] != "All":
                display_header_labels.append(f"{original_label} (F)")
            else:
                display_header_labels.append(original_label)

        self.task_table.setHorizontalHeaderLabels(display_header_labels)
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch) # Ensure columns stretch

        for row_idx, row in enumerate(data):
            for col_idx, col_val in enumerate(row):
                self.task_table.setItem(row_idx, col_idx, QTableWidgetItem(str(col_val)))


    def populate_task_fields(self):
        selected = self.task_table.currentRow()
        if selected >= 0:
            self.title_input.setText(self.task_table.item(selected, 1).text())
            self.desc_input.setText(self.task_table.item(selected, 2).text())
            self.start_input.setDate(datetime.strptime(self.task_table.item(selected, 3).text(), "%Y-%m-%d").date())
            self.due_input.setDate(datetime.strptime(self.task_table.item(selected, 4).text(), "%Y-%m-%d").date())
            self.status_input.setCurrentText(self.task_table.item(selected, 5).text())
            self.owner_input.setCurrentText(self.task_table.item(selected, 6).text())
            self.priority_input.setCurrentText(self.task_table.item(selected, 7).text())
            project_text = self.task_table.item(selected, 8).text()
            index = self.project_input.findText(project_text)
            if index != -1:
                self.project_input.setCurrentIndex(index)
            else:
                self.project_input.setCurrentText("")
        # No need to call self.header_view.viewport().update() here as load_tasks is called on filter change.

    def add_task(self):
        if not self.sanity_check_task_fields():
            return
        run_query("""
            INSERT INTO tasks (title, description, start_date, due_date, status, owner, priority, project)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.title_input.text(), self.desc_input.text(),
                self.start_input.date().toString("yyyy-MM-dd"), self.due_input.date().toString("yyyy-MM-dd"),
                self.status_input.currentText(), self.owner_input.currentText(),
                self.priority_input.currentText(), self.project_input.currentText()
            )
        )
        self.load_tasks()
        # No need to call self.header_view.viewport().update() here as load_tasks updates labels directly

    def update_task(self):
        selected = self.task_table.currentRow()
        if selected >= 0:
            if not self.sanity_check_task_fields():
                return
            task_id = self.task_table.item(selected, 0).text()
            run_query("""
                UPDATE tasks
                SET title=?, description=?, start_date=?, due_date=?, status=?, owner=?, priority=?, project=?
                WHERE id=?""",
                (
                    self.title_input.text(), self.desc_input.text(),
                    self.start_input.date().toString("yyyy-MM-dd"), self.due_input.date().toString("yyyy-MM-dd"),
                    self.status_input.currentText(), self.owner_input.currentText(),
                    self.priority_input.currentText(), self.project_input.currentText(),
                    task_id
                )
            )
            self.load_tasks()
            # No need to call self.header_view.viewport().update() here as load_tasks updates labels directly
        else:
            QMessageBox.warning(self, "Error", "Select a task to update")

    def delete_task(self):
        selected = self.task_table.currentRow()
        if selected >= 0:
            task_name = self.task_table.item(selected, 1).text()
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete this task: '{task_name}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                task_id = self.task_table.item(selected, 0).text()
                run_query("DELETE FROM tasks WHERE id = ?", (task_id,))
                self.load_tasks()
                QMessageBox.information(self, "Done", "Task deleted")
                # No need to call self.header_view.viewport().update() here as load_tasks updates labels directly
        else:
            QMessageBox.warning(self, "Error", "Select a task to delete")

    def sanity_check_task_fields(self):
        title = self.title_input.text().strip()
        desc = self.desc_input.text().strip()
        start = self.start_input.date()
        due = self.due_input.date()
        owner = self.owner_input.currentText().strip()
        project = self.project_input.currentText().strip()
        if not title or not desc or not owner or not project:
            QMessageBox.warning(self, "Validation Error", "Title, Description, Owner and Project cannot be blank.")
            return False
        if due < start:
            QMessageBox.warning(self, "Validation Error", "Due date cannot be earlier than Start date.")
            return False
        return True

    def update_user_combobox(self):
        self.owner_input.clear()
        users = run_query("SELECT username FROM users", fetch=True)
        self.owner_input.addItems([u[0] for u in users])

    def update_project_combobox(self):
        self.project_input.clear()
        projects = run_query("SELECT project_name FROM projects", fetch=True)
        self.project_input.addItems([p[0] for p in projects])


    # --- USER TAB ---
    def init_user_tab(self):
        layout = QVBoxLayout()
        self.user_input = QLineEdit()
        add_user_btn = QPushButton("Add User")
        del_user_btn = QPushButton("Delete User")
        self.reassign_from_combo = QComboBox()
        self.reassign_to_combo = QComboBox()
        reassign_btn = QPushButton("Reassign Open Tasks")

        add_user_btn.clicked.connect(lambda: self.modify_user("add"))
        del_user_btn.clicked.connect(self.delete_user_selected)
        reassign_btn.clicked.connect(self.reassign_tasks)

        layout.addWidget(QLabel("Username"))
        layout.addWidget(self.user_input)
        layout.addWidget(add_user_btn)
        layout.addWidget(del_user_btn)

        layout.addWidget(QLabel("Reassign open tasks from:"))
        layout.addWidget(self.reassign_from_combo)
        layout.addWidget(QLabel("to:"))
        layout.addWidget(self.reassign_to_combo)
        layout.addWidget(reassign_btn)

        self.user_table = QTableWidget()
        layout.addWidget(self.user_table)

        self.user_tab.setLayout(layout)
        self.load_users()

    def load_users(self):
        data = run_query("SELECT username FROM users ORDER BY username", fetch=True)
        self.user_table.setRowCount(len(data))
        self.user_table.setColumnCount(1)
        self.user_table.setHorizontalHeaderLabels(["Username"])
        for r, row in enumerate(data):
            self.user_table.setItem(r, 0, QTableWidgetItem(row[0]))
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Update user combos
        users = [u[0] for u in data]
        self.reassign_from_combo.clear()
        self.reassign_to_combo.clear()
        self.reassign_from_combo.addItems(users)
        self.reassign_to_combo.addItems(users)

    def modify_user(self, action):
        user = self.user_input.text().strip()
        if not user:
            QMessageBox.warning(self, "Error", "Username cannot be empty")
            return
        if action == "add":
            run_query("INSERT OR IGNORE INTO users (username) VALUES (?)", (user,))
            QMessageBox.information(self, "Done", f"User added: {user}")
        self.load_users()

    def delete_user_selected(self):
        selected = self.user_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Select a user from the table to delete")
            return
        user = self.user_table.item(selected, 0).text()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete user: '{user}'?\nNote: tasks assigned to this user will remain unchanged.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            run_query("DELETE FROM users WHERE username = ?", (user,))
            self.load_users()
            self.update_user_combobox()
            QMessageBox.information(self, "Done", f"User deleted: {user}")

    def reassign_tasks(self):
        from_user = self.reassign_from_combo.currentText()
        to_user = self.reassign_to_combo.currentText()
        if from_user == to_user:
            QMessageBox.warning(self, "Error", "Source and target user must be different.")
            return
        reply = QMessageBox.question(
            self, "Confirm Reassign",
            f"Reassign all open tasks from '{from_user}' to '{to_user}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            run_query("UPDATE tasks SET owner = ? WHERE owner = ? AND status != 'Done'", (to_user, from_user))
            QMessageBox.information(self, "Done", f"Open tasks reassigned from {from_user} to {to_user}.")
            self.load_tasks()
            self.load_users()
            self.update_user_combobox()

    # --- HOLIDAY TAB ---
    def init_holiday_tab(self):
        layout = QVBoxLayout()
        self.hol_date = QDateEdit(calendarPopup=True)
        self.hol_date.setDate(date.today())
        self.hol_name = QLineEdit()
        add_btn = QPushButton("Add Holiday")
        del_btn = QPushButton("Delete Holiday")
        add_btn.clicked.connect(self.add_holiday)
        del_btn.clicked.connect(self.delete_holiday)
        layout.addWidget(QLabel("Date"))
        layout.addWidget(self.hol_date)
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.hol_name)
        layout.addWidget(add_btn)
        layout.addWidget(del_btn)

        self.holiday_table = QTableWidget()
        layout.addWidget(self.holiday_table)
        self.load_holidays()
        self.holiday_tab.setLayout(layout)

    def add_holiday(self):
        if not self.hol_name.text().strip():
            QMessageBox.warning(self, "Validation Error", "Holiday name cannot be empty.")
            return
        run_query("INSERT INTO holidays (date, name) VALUES (?, ?)",
                  (self.hol_date.date().toString("yyyy-MM-dd"), self.hol_name.text()))
        self.load_holidays()

    def delete_holiday(self):
        selected = self.holiday_table.currentRow()
        if selected >= 0:
            holiday_id = self.holiday_table.item(selected, 0).text()
            reply = QMessageBox.question(
                self, "Confirm Delete",
                "Are you sure you want to delete the selected holiday?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                run_query("DELETE FROM holidays WHERE id = ?", (holiday_id,))
                self.load_holidays()
                QMessageBox.information(self, "Done", f"Holiday deleted")
        else:
            QMessageBox.warning(self, "Error", "Select a holiday to delete")

    def load_holidays(self):
        data = run_query("SELECT id, date, name FROM holidays ORDER BY date", fetch=True)
        self.holiday_table.setRowCount(len(data))
        self.holiday_table.setColumnCount(3)
        self.holiday_table.setHorizontalHeaderLabels(["ID", "Date", "Name"])
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.holiday_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.holiday_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    # --- PROJECT TAB ---
    def init_project_tab(self):
        layout = QVBoxLayout()
        self.project_input_name = QLineEdit()
        add_project_btn = QPushButton("Add Project")
        del_project_btn = QPushButton("Delete Project")

        add_project_btn.clicked.connect(self.add_project)
        del_project_btn.clicked.connect(self.delete_project_selected)

        layout.addWidget(QLabel("Project Name"))
        layout.addWidget(self.project_input_name)
        layout.addWidget(add_project_btn)
        layout.addWidget(del_project_btn)

        self.project_table = QTableWidget()
        layout.addWidget(self.project_table)

        self.project_tab.setLayout(layout)
        self.load_projects()

    def load_projects(self):
        data = run_query("SELECT project_name FROM projects ORDER BY project_name", fetch=True)
        self.project_table.setRowCount(len(data))
        self.project_table.setColumnCount(1)
        self.project_table.setHorizontalHeaderLabels(["Project Name"])
        for r, row in enumerate(data):
            self.project_table.setItem(r, 0, QTableWidgetItem(row[0]))
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.update_project_combobox()
        self.update_project_filter_combobox()
        self.update_export_project_filter_combobox()

    def add_project(self):
        project_name = self.project_input_name.text().strip()
        if not project_name:
            QMessageBox.warning(self, "Error", "Project name cannot be empty")
            return
        run_query("INSERT OR IGNORE INTO projects (project_name) VALUES (?)", (project_name,))
        QMessageBox.information(self, "Done", f"Project added: {project_name}")
        self.load_projects()

    def delete_project_selected(self):
        selected = self.project_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Select a project from the table to delete")
            return
        project_name = self.project_table.item(selected, 0).text()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete project: '{project_name}'?\nNote: tasks assigned to this project will remain unchanged.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            run_query("DELETE FROM projects WHERE project_name = ?", (project_name,))
            self.load_projects()
            self.update_project_combobox()
            self.update_project_filter_combobox()
            self.update_export_project_filter_combobox()
            QMessageBox.information(self, "Done", f"Project deleted: {project_name}")


    # --- GANTT TAB ---
    def init_gantt_tab(self):
        layout = QVBoxLayout()
        filter_layout = QHBoxLayout()

        self.gantt_start_date = QDateEdit(calendarPopup=True)
        self.gantt_end_date = QDateEdit(calendarPopup=True)
        self.status_filter = QComboBox()
        self.user_filter = QComboBox()
        self.project_filter = QComboBox()

        self.status_filter.addItems(["All", "Open", "Done"])
        self.user_filter.addItem("All")
        self.project_filter.addItem("All")

        self.set_gantt_default_start_date() # Call the new method to set the default start date
        self.gantt_end_date.setDate(date.today() + timedelta(days=30))

        self.update_user_filter_combobox()
        self.update_project_filter_combobox()

        filter_layout.addWidget(QLabel("Start Date:"))
        filter_layout.addWidget(self.gantt_start_date)
        filter_layout.addWidget(QLabel("End Date:"))
        filter_layout.addWidget(self.gantt_end_date)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.status_filter)
        filter_layout.addWidget(QLabel("User:"))
        filter_layout.addWidget(self.user_filter)
        filter_layout.addWidget(QLabel("Project:"))
        filter_layout.addWidget(self.project_filter)

        btn_layout = QHBoxLayout()
        draw_btn = QPushButton("Draw Gantt Chart")
        export_pdf_btn = QPushButton("Export to PDF")
        draw_btn.clicked.connect(self.draw_gantt)
        export_pdf_btn.clicked.connect(self.export_gantt_pdf)
        btn_layout.addWidget(draw_btn)
        btn_layout.addWidget(export_pdf_btn)

        self.canvas = FigureCanvas(plt.figure(figsize=(10, 5)))

        layout.addLayout(filter_layout)
        layout.addLayout(btn_layout)
        layout.addWidget(self.canvas)
        self.gantt_tab.setLayout(layout)

    def set_gantt_default_start_date(self):
        # Option 1: Today - 1 working day
        today_minus_1_working_day = get_working_day_before(date.today())

        # Option 2: The end date of the oldest open item
        oldest_open_task_due_date = None
        oldest_task_data = run_query("SELECT due_date FROM tasks WHERE status = 'Open' ORDER BY due_date ASC LIMIT 1", fetch=True)
        if oldest_task_data and oldest_task_data[0][0]:
            oldest_open_task_due_date = datetime.strptime(oldest_task_data[0][0], "%Y-%m-%d").date()

        # Determine the earliest date
        if oldest_open_task_due_date and oldest_open_task_due_date < today_minus_1_working_day:
            default_start = oldest_open_task_due_date
        else:
            default_start = today_minus_1_working_day
            
        self.gantt_start_date.setDate(default_start)


    def update_user_filter_combobox(self):
        users = run_query("SELECT username FROM users", fetch=True)
        self.user_filter.clear()
        self.user_filter.addItem("All")
        self.user_filter.addItems([u[0] for u in users])

    def update_project_filter_combobox(self):
        projects = run_query("SELECT project_name FROM projects", fetch=True)
        self.project_filter.clear()
        self.project_filter.addItem("All")
        self.project_filter.addItems([p[0] for p in projects])

    def draw_gantt(self):
        start_date_plot = self.gantt_start_date.date().toPyDate() # Get as Python date object
        end_date_plot = self.gantt_end_date.date().toPyDate() # Get as Python date object
        
        status = self.status_filter.currentText()
        user = self.user_filter.currentText()
        project = self.project_filter.currentText()

        query = "SELECT title, start_date, due_date, status, owner, project FROM tasks WHERE start_date <= ? AND due_date >= ?"
        params = [end_date_plot.strftime("%Y-%m-%d"), start_date_plot.strftime("%Y-%m-%d")] # Convert back for DB query

        if status != "All":
            query += " AND status = ?"
            params.append(status)
        if user != "All":
            query += " AND owner = ?"
            params.append(user)
        if project != "All":
            query += " AND project = ?"
            params.append(project)

        tasks = run_query(query, params, fetch=True)

        fig = self.canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        if not tasks:
            ax.text(0.5, 0.5, "No tasks for selected filters", ha="center", va="center", fontsize=14)
            self.canvas.draw()
            return

        y_labels = []
        y_pos = []
        bars = []
        colors = []
        
        today = date.today()

        for i, (title, start, due, stat, owner, proj) in enumerate(tasks):
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
            due_dt = datetime.strptime(due, "%Y-%m-%d").date()
            duration = (due_dt - start_dt).days + 1
            y_labels.append(f"{title}\n({owner} / {proj})")
            y_pos.append(i)
            bars.append((start_dt, duration))

            if stat == "Done":
                colors.append("green")
            elif due_dt < today and stat != "Done":
                colors.append("red")
            elif due_dt == today and stat != "Done":
                colors.append("orange")
            else:
                colors.append("blue")


        # Plot bars
        for i, (start_dt, duration) in enumerate(bars):
            ax.barh(y_pos[i], duration, left=start_dt, color=colors[i], edgecolor='black')

        # Highlight weekends and holidays as grey vertical bands
        ax.set_xlim(start_date_plot, end_date_plot) # Use Python date objects directly for plotting limits
        ax.set_yticks(y_pos)
        ax.set_yticklabels(y_labels)

        # Draw grey bands for weekends
        current_day = start_date_plot
        while current_day <= end_date_plot:
            if current_day.weekday() >= 5: # Saturday (5) or Sunday (6)
                ax.axvspan(current_day, current_day + timedelta(days=1), color='grey', alpha=0.3)
            current_day += timedelta(days=1)

        # Draw grey bands for holidays
        holidays = run_query("SELECT date FROM holidays", fetch=True)
        for (hol_date_str,) in holidays:
            hol_date = datetime.strptime(hol_date_str, "%Y-%m-%d").date()
            if start_date_plot <= hol_date <= end_date_plot:
                ax.axvspan(hol_date, hol_date + timedelta(days=1), color='grey', alpha=0.5)

        # Add light yellow bar for current day
        if start_date_plot <= today <= end_date_plot:
            ax.axvspan(today, today + timedelta(days=1), color='yellow', alpha=0.3)
        
        # Add daily grid lines for all days (minor ticks)
        ax.xaxis.set_minor_locator(mdates.DayLocator())
        ax.xaxis.grid(True, which='both', linestyle='--', alpha=0.7)

        # Set x-axis major ticks to show only Mondays
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MONDAY, interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate() # Auto-format date labels

        ax.set_xlabel("Date")
        ax.invert_yaxis()
        fig.tight_layout()
        self.canvas.draw()

    def export_gantt_pdf(self):
        start_date_plot = self.gantt_start_date.date().toPyDate()
        end_date_plot = self.gantt_end_date.date().toPyDate()
        
        status = self.status_filter.currentText()
        user = self.user_filter.currentText()
        project = self.project_filter.currentText()

        query = "SELECT title, start_date, due_date, status, owner, project FROM tasks WHERE start_date <= ? AND due_date >= ?"
        params = [end_date_plot.strftime("%Y-%m-%d"), start_date_plot.strftime("%Y-%m-%d")]

        if status != "All":
            query += " AND status = ?"
            params.append(status)
        if user != "All":
            query += " AND owner = ?"
            params.append(user)
        if project != "All":
            query += " AND project = ?"
            params.append(project)

        tasks = run_query(query, params, fetch=True)

        if not tasks:
            QMessageBox.information(self, "No Data", "No tasks to export for selected filters.")
            return

        fig, ax = plt.subplots(figsize=(11, 8.5)) # Letter size
        
        y_labels = []
        y_pos = []
        bars = []
        colors = []

        today = date.today()

        for i, (title, start, due, stat, owner, proj) in enumerate(tasks):
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
            due_dt = datetime.strptime(due, "%Y-%m-%d").date()
            duration = (due_dt - start_dt).days + 1
            y_labels.append(f"{title}\n({owner} / {proj})")
            y_pos.append(i)
            bars.append((start_dt, duration))

            if stat == "Done":
                colors.append("green")
            elif due_dt < today and stat != "Done":
                colors.append("red")
            elif due_dt == today and stat != "Done":
                colors.append("orange")
            else:
                colors.append("blue")

        for i, (start_dt, duration) in enumerate(bars):
            ax.barh(y_pos[i], duration, left=start_dt, color=colors[i], edgecolor='black')

        ax.set_xlim(start_date_plot, end_date_plot)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(y_labels, fontsize=8) # Set font size for y-axis labels

        current_day = start_date_plot
        while current_day <= end_date_plot:
            if current_day.weekday() >= 5: # Saturday (5) or Sunday (6)
                ax.axvspan(current_day, current_day + timedelta(days=1), color='grey', alpha=0.3)
            current_day += timedelta(days=1)

        holidays = run_query("SELECT date FROM holidays", fetch=True)
        for (hol_date_str,) in holidays:
            hol_date = datetime.strptime(hol_date_str, "%Y-%m-%d").date()
            if start_date_plot <= hol_date <= end_date_plot:
                ax.axvspan(hol_date, hol_date + timedelta(days=1), color='grey', alpha=0.5)

        # Add light yellow bar for current day
        if start_date_plot <= today <= end_date_plot:
            ax.axvspan(today, today + timedelta(days=1), color='yellow', alpha=0.3)
        
        # Add daily grid lines for all days (minor ticks)
        ax.xaxis.set_minor_locator(mdates.DayLocator())
        ax.xaxis.grid(True, which='both', linestyle='--', alpha=0.7)

        # Set x-axis major ticks to show only Mondays
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MONDAY, interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate() # Auto-format date labels

        ax.set_xlabel("Date", fontsize=10) # Set font size for x-axis label
        
        # Create dynamic title
        filter_parts = []
        filter_parts.append(f"Date Range: {start_date_plot.strftime('%Y-%m-%d')} to {end_date_plot.strftime('%Y-%m-%d')}")
        if status != "All":
            filter_parts.append(f"Status: {status}")
        if user != "All":
            filter_parts.append(f"User: {user}")
        if project != "All":
            filter_parts.append(f"Project: {project}")
        
        dynamic_title = "Task Gantt Chart\n" + ", ".join(filter_parts)
        ax.set_title(dynamic_title, fontsize=12) # Add title with font size
        
        ax.invert_yaxis()
        fig.tight_layout()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            fig.savefig(tmp.name)
            plt.close(fig)
            os.startfile(tmp.name)

    # --- EXPORT TAB ---
    def init_export_tab(self):
        layout = QVBoxLayout()

        filter_layout = QHBoxLayout()
        self.export_start_date = QDateEdit(calendarPopup=True)
        self.export_end_date = QDateEdit(calendarPopup=True)
        self.export_status_filter = QComboBox()
        self.export_user_filter = QComboBox()
        self.export_project_filter = QComboBox()

        self.export_status_filter.addItems(["All", "Open", "Done"])
        self.export_user_filter.addItem("All")
        self.export_project_filter.addItem("All")

        self.export_start_date.setDate(get_working_day_before(date.today()))
        self.export_end_date.setDate(date.today() + timedelta(days=30))

        self.update_export_user_filter_combobox()
        self.update_export_project_filter_combobox()

        filter_layout.addWidget(QLabel("Start Date:"))
        filter_layout.addWidget(self.export_start_date)
        filter_layout.addWidget(QLabel("End Date:"))
        filter_layout.addWidget(self.export_end_date)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.export_status_filter)
        filter_layout.addWidget(QLabel("User:"))
        filter_layout.addWidget(self.export_user_filter)
        filter_layout.addWidget(QLabel("Project:"))
        filter_layout.addWidget(self.export_project_filter)

        btn_layout = QHBoxLayout()
        to_excel_btn = QPushButton("Export Tasks to Excel")
        to_pdf_btn = QPushButton("Export Tasks to PDF")
        to_excel_btn.clicked.connect(self.export_excel)
        to_pdf_btn.clicked.connect(self.export_pdf)
        btn_layout.addWidget(to_excel_btn)
        btn_layout.addWidget(to_pdf_btn)

        layout.addLayout(filter_layout)
        layout.addLayout(btn_layout)
        self.export_tab.setLayout(layout)

    def update_export_user_filter_combobox(self):
        users = run_query("SELECT username FROM users", fetch=True)
        self.export_user_filter.clear()
        self.export_user_filter.addItem("All")
        self.export_user_filter.addItems([u[0] for u in users])

    def update_export_project_filter_combobox(self):
        projects = run_query("SELECT project_name FROM projects", fetch=True)
        self.export_project_filter.clear()
        self.export_project_filter.addItem("All")
        self.export_project_filter.addItems([p[0] for p in projects])

    def export_excel(self):
        start_date = self.export_start_date.date().toString("yyyy-MM-dd")
        end_date = self.export_end_date.date().toString("yyyy-MM-dd")
        status = self.export_status_filter.currentText()
        user = self.export_user_filter.currentText()
        project = self.export_project_filter.currentText()

        query = "SELECT title, description, start_date, due_date, status, owner, priority, project FROM tasks WHERE start_date <= ? AND due_date >= ?"
        params = [end_date, start_date]

        if status != "All":
            query += " AND status = ?"
            params.append(status)
        if user != "All":
            query += " AND owner = ?"
            params.append(user)
        if project != "All":
            query += " AND project = ?"
            params.append(project)

        data = run_query(query, params, fetch=True)

        if not data:
            QMessageBox.information(self, "No Data", "No tasks to export for selected filters.")
            return

        df = pd.DataFrame(data, columns=["Title", "Description", "Start Date", "Due Date", "Status", "Owner", "Priority", "Project"])

        file_name, _ = QFileDialog.getSaveFileName(self, "Export to Excel", "tasks.xlsx", "Excel Files (*.xlsx)")
        if file_name:
            df.to_excel(file_name, index=False)
            QMessageBox.information(self, "Export Complete", f"Tasks exported to {file_name}")

    def export_pdf(self):
        start_date = self.export_start_date.date().toString("yyyy-MM-dd")
        end_date = self.export_end_date.date().toString("yyyy-MM-dd")
        status = self.export_status_filter.currentText()
        user = self.export_user_filter.currentText()
        project = self.export_project_filter.currentText()

        query = "SELECT title, description, start_date, due_date, status, owner, priority, project FROM tasks WHERE start_date <= ? AND due_date >= ?"
        params = [end_date, start_date]

        if status != "All":
            query += " AND status = ?"
            params.append(status)
        if user != "All":
            query += " AND owner = ?"
            params.append(user)
        if project != "All":
            query += " AND project = ?"
            params.append(project)

        data = run_query(query, params, fetch=True)

        if not data:
            QMessageBox.information(self, "No Data", "No tasks to export for selected filters.")
            return

        df = pd.DataFrame(data, columns=["Title", "Description", "Start Date", "Due Date", "Status", "Owner", "Priority", "Project"])

        file_name, _ = QFileDialog.getSaveFileName(self, "Export to PDF", "tasks.pdf", "PDF Files (*.pdf)")
        if file_name:
            fig, ax = plt.subplots(figsize=(11, 8.5)) # Letter size
            ax.axis('off')
            ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='left')
            fig.tight_layout()
            fig.savefig(file_name)
            plt.close(fig)
            QMessageBox.information(self, "Export Complete", f"Tasks exported to {file_name}")

    # --- ABOUT TAB ---
    def init_about_tab(self):
        layout = QVBoxLayout()

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logo.jpg")
        logo_label = QLabel()
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaledToWidth(300, Qt.SmoothTransformation))
                logo_label.setAlignment(Qt.AlignCenter)
            else:
                logo_label.setText("Error loading Logo.jpg (file exists but image data is invalid)")
                logo_label.setAlignment(Qt.AlignCenter)
        else:
            logo_label.setText("Logo.jpg not found in application directory.")
            logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        about_text = QLabel(
            "Task Tracker Application V2.3\n\n"
            "Developed by Bob Berry of Berry Tech\n\n"
            "robert.berry@bgcg.com\n\n"
            "\n\n"
            "v2.3 updates: \n\n"
            "Changes made to Gannt graph start date logic \n\n"
			"v2.2 updates: \n\n"
            "Minor changes to gantt graph (Today line) \n\n"
			"Filtering added to tasks page \n\n"
            "v2.1 updates: \n\n"
            "Projects added to tasks and filters \n\n"
            "\n\n"
            "\n\n"
            "Remember - Laziness drives innovation"
        )
        about_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(about_text)
        layout.addStretch()
        self.about_tab.setLayout(layout)

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)

    # --- Splash Screen Implementation ---
    splash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Splash.jpg")
    splash_pixmap = QPixmap(splash_path)
    splash = None

    if os.path.exists(splash_path) and not splash_pixmap.isNull():
        splash = QSplashScreen(splash_pixmap, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()
    else:
        print(f"Warning: Splash.jpg not found or could not be loaded from {splash_path}. Continuing without splash screen.")

    window = TaskTrackerApp()
    window.show()

    if splash:
        splash.finish(window)

    sys.exit(app.exec_())

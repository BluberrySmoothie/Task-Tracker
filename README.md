# Task Tracker V2.3

A powerful desktop application for managing tasks, projects, and team workflows with visual Gantt charts and comprehensive export capabilities.

## Features

- **Task Management**: Create, edit, and track tasks with detailed information including title, description, dates, priority, and status
- **User Management**: Manage team members and reassign tasks between users
- **Project Organization**: Organize tasks into projects for better structure and tracking
- **Gantt Chart Visualization**: Generate interactive Gantt charts with color-coded task status and holiday/weekend highlighting
- **Holiday Calendar**: Maintain a holiday calendar that integrates with Gantt chart visualization
- **Advanced Filtering**: Filter tasks by status, owner, priority, and project simultaneously
- **Data Export**: Export tasks to Excel or PDF formats with custom filtering
- **Data Persistence**: All data stored locally in SQLite database

## System Requirements

- **OS**: Windows 7 or later
- **Python**: 3.7 or higher
- **RAM**: 2 GB minimum
- **Disk Space**: 500 MB

## Installation

### Prerequisites

Ensure you have Python 3.7+ installed. Download from [python.org](https://www.python.org/downloads/)

### Steps

1. Clone or download the Task Tracker repository:
   ```bash
   git clone https://github.com/yourusername/task-tracker.git
   cd task-tracker
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   Or install manually:
   ```bash
   pip install PyQt5>=5.12 pandas>=1.0 matplotlib>=3.0 openpyxl
   ```

4. Run the application:
   ```bash
   python task_tracker.py
   ```

### Optional Files

Place these optional files in the application directory for enhanced UI:
- `Logo.jpg`: Application logo (displayed in About tab)
- `Splash.jpg`: Splash screen image (displayed on startup)

## Usage Guide

### Main Tabs

#### Tasks Tab
- **Add Task**: Fill in task details and click "Add Task"
- **Update Task**: Select a task and modify its details, then click "Update Task"
- **Delete Task**: Select a task and click "Delete Task"
- **Filter Tasks**: Click on column headers (Status, Owner, Priority, Project) to filter
  - Filtered columns display "(F)" indicator in header
  - Select "All" to clear filter for that column

Required fields: Title, Description, Owner, Project

#### Users Tab
- **Add User**: Enter username and click "Add User"
- **Delete User**: Select user and click "Delete User"
- **Reassign Tasks**: Select source and target users, then click "Reassign Open Tasks"
  - Only reassigns tasks with "Open" status

#### Projects Tab
- **Add Project**: Enter project name and click "Add Project"
- **Delete Project**: Select project and click "Delete Project"
- Note: Deleting a project doesn't delete associated tasks

#### Holidays Tab
- **Add Holiday**: Select date, enter holiday name, and click "Add Holiday"
- **Delete Holiday**: Select holiday and click "Delete Holiday"
- Holidays are highlighted in Gantt charts

#### Gantt Chart Tab
- Set date range using "Start Date" and "End Date"
- Filter by Status, Owner, or Project
- Click "Draw Gantt Chart" to generate visualization
- Click "Export to PDF" to save chart as PDF

**Color Coding**:
- 🟢 Green: Completed tasks
- 🔴 Red: Overdue tasks
- 🟠 Orange: Tasks due today
- 🔵 Blue: On-time tasks

#### Export Tab
- Set date range and filters (Status, Owner, Project)
- Click "Export Tasks to Excel" for .xlsx format
- Click "Export Tasks to PDF" for PDF format
- Save dialog allows you to choose file location and name

### Data Validation

The application enforces the following rules:
- Title, Description, Owner, and Project are mandatory
- Due date must be equal to or later than start date
- Usernames and project names cannot be empty
- Holiday names cannot be empty

## Database

- **Location**: `task_tracker.db3` (created in application directory)
- **Engine**: SQLite3
- **Auto-initialization**: Database tables are created automatically on first run
- **No setup required**: Simply run the application

### Tables

| Table | Columns | Purpose |
|-------|---------|---------|
| users | username | Store user/team member information |
| tasks | id, title, description, start_date, due_date, status, owner, priority, project | Store task details |
| holidays | id, date, name | Store holiday calendar |
| projects | project_name | Store project names |

## Troubleshooting

### Application won't start
- Verify Python 3.7+ is installed: `python --version`
- Check all dependencies are installed: `pip install -r requirements.txt`
- Ensure you're in the correct directory

### Database errors
- Delete `task_tracker.db3` to reset database (WARNING: This deletes all data)
- Check disk space and file permissions in application directory

### Gantt chart not displaying
- Verify tasks have valid start and due dates
- Ensure at least one task matches filter criteria
- Check that date range includes task dates

### Export fails
- Verify write permissions in target directory
- Ensure sufficient disk space
- Close any existing exported files that might be locked

### Missing splash screen or logo
- Ensure `Splash.jpg` and `Logo.jpg` are in application directory
- Application functions normally without these files (warnings displayed)

## Performance Tips

- For better performance with large datasets (1000+ tasks):
  - Use date range filters to limit visible tasks
  - Consider archiving completed tasks in separate database
- Gantt charts render faster with smaller date ranges

## File Structure

```
task-tracker/
├── task_tracker.py          # Main application file
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── Logo.jpg                # Application logo (optional)
├── Splash.jpg              # Splash screen (optional)
└── task_tracker.db3        # SQLite database (auto-created)
```

## Development

### Project Stack
- **GUI Framework**: PyQt5
- **Database**: SQLite3
- **Data Processing**: pandas
- **Visualization**: matplotlib
- **Export Formats**: Excel (openpyxl), PDF (matplotlib)

### Code Structure
- Database initialization and helpers at top of file
- Custom header view class for filtering
- Main application class (TaskTrackerApp) with tab initialization methods
- Tab-specific methods organized by functionality

## Version History

- **V2.3**: Updated Gantt chart start date logic
- **V2.2**: Added today line indicator to Gantt chart, filtering added to tasks page
- **V2.1**: Projects added to tasks and filters

## About

**Task Tracker V2.3**

Developed by BluBerry Smoothie

Contact: https://github.com/BluberrySmoothie

*"Remember - Laziness drives innovation"*

## License

[Your License Here]

## Support & Feedback

For issues, feature requests, or feedback:
- Report bugs with detailed description and steps to reproduce

## Frequently Asked Questions

**Q: Can I use this on Mac or Linux?**
A: The current version is Windows-only due to file handling (os.startfile). Porting would require cross-platform modifications.

**Q: Can multiple people use this simultaneously?**
A: No, this is a single-user desktop application. Using shared network folders is not recommended due to SQLite limitations.

**Q: How do I back up my data?**
A: Simply copy the `task_tracker.db3` file to another location for backup.

**Q: Can I import data from other sources?**
A: Currently, you must manually enter data or create a custom import script to populate the database.

**Q: What happens if I delete a user?**
A: The user is removed, but their assigned tasks remain in the database with their username preserved.

---

**Last Updated**: October 2024

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QPushButton, QLabel, QLineEdit, QListWidgetItem,
    QSplitter, QCalendarWidget, QTimeEdit, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTime
from PyQt6.QtGui import QAction
import sys
import json
import datetime as dt
from notifypy import Notify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import ConflictingIdError
import os

DATA_FILE = "todo_data.json"


class TodoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modern To‑Do • Special To‑Do List")
        self.resize(1000, 650)

        # In-memory model: { title: {"tasks": [str], "reminder":
        # iso_datetime_or_empty} }
        self.lists = {}

        # Background scheduler for reminders
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        # UI
        self._build_ui()

        # Load saved lists and schedule pending reminders
        self._load_data()
        self._schedule_existing_reminders()

    def _build_ui(self):
        # Main splitter: left = sidebar, right = content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QFrame()
        sidebar.setMaximumWidth(300)
        sidebar.setMinimumWidth(240)
        sidebar_layout = QVBoxLayout()
        sidebar.setLayout(sidebar_layout)

        # Sidebar header
        header = QLabel("My Lists")
        header.setObjectName("sidebarHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(header)

        # Lists widget
        self.lists_widget = QListWidget()
        self.lists_widget.itemSelectionChanged.connect(self._on_list_selected)
        sidebar_layout.addWidget(self.lists_widget, stretch=1)

        # Sidebar buttons
        sb_btn_layout = QHBoxLayout()
        add_list_btn = QPushButton("New")
        add_list_btn.clicked.connect(self._create_list_dialog)
        remove_list_btn = QPushButton("Delete")
        remove_list_btn.clicked.connect(self._delete_selected_list)
        sb_btn_layout.addWidget(add_list_btn)
        sb_btn_layout.addWidget(remove_list_btn)
        sidebar_layout.addLayout(sb_btn_layout)

        # Quick save/load actions
        save_btn = QPushButton("Save All")
        save_btn.clicked.connect(self._save_data)
        sidebar_layout.addWidget(save_btn)

        splitter.addWidget(sidebar)

        # Content area
        content = QWidget()
        content_layout = QVBoxLayout()
        content.setLayout(content_layout)

        # Title and controls
        title_bar = QHBoxLayout()
        self.title_label = QLabel("Select or create a list")
        self.title_label.setObjectName("titleLabel")
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()
        # Action to mark list as done (simple visual)
        mark_done_btn = QPushButton("Mark Done")
        mark_done_btn.clicked.connect(self._mark_list_done)
        title_bar.addWidget(mark_done_btn)
        content_layout.addLayout(title_bar)

        # Tasks area
        tasks_area = QHBoxLayout()
        left_tasks = QVBoxLayout()
        self.tasks_widget = QListWidget()
        left_tasks.addWidget(self.tasks_widget, stretch=1)

        add_task_layout = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Add a task and press Add")
        add_task_btn = QPushButton("Add")
        add_task_btn.clicked.connect(self._add_task_to_current_list)
        add_task_layout.addWidget(self.task_input)
        add_task_layout.addWidget(add_task_btn)
        left_tasks.addLayout(add_task_layout)

        remove_task_btn = QPushButton("Remove Selected Task")
        remove_task_btn.clicked.connect(self._remove_selected_task)
        left_tasks.addWidget(remove_task_btn)

        tasks_area.addLayout(left_tasks, stretch=2)

        # Right area: mini calendar + time + schedule button
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Schedule a reminder"))

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        right_panel.addWidget(self.calendar)

        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        right_panel.addWidget(self.time_edit)

        schedule_btn = QPushButton("Set Reminder for this list")
        schedule_btn.clicked.connect(self._schedule_reminder_for_current_list)
        right_panel.addWidget(schedule_btn)

        clear_reminder_btn = QPushButton("Clear Reminder")
        clear_reminder_btn.clicked.connect(
            self._clear_reminder_for_current_list)
        right_panel.addWidget(clear_reminder_btn)

        # Small label to show scheduled datetime
        self.reminder_info = QLabel("")
        right_panel.addWidget(self.reminder_info)
        right_panel.addStretch()

        tasks_area.addLayout(right_panel, stretch=1)

        content_layout.addLayout(tasks_area, stretch=1)

        # Bottom action row: title edit, save list
        bottom_row = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Edit list title (press Rename)")
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_current_list)
        save_list_btn = QPushButton("Save List")
        save_list_btn.clicked.connect(self._save_data)
        bottom_row.addWidget(self.title_edit)
        bottom_row.addWidget(rename_btn)
        bottom_row.addWidget(save_list_btn)
        content_layout.addLayout(bottom_row)

        splitter.addWidget(content)
        self.setCentralWidget(splitter)

        # Styling (simple modern look)
        self.setStyleSheet(
            """
            QMainWindow { background: #f6f7fb; }
            #sidebarHeader { font-weight: bold; font-size: 16px; padding: 8px; }
            QListWidget { background: #ffffff; border-radius: 6px; padding: 6px; }
            QPushButton { padding: 6px 8px; border-radius: 6px; }
            #titleLabel { font-size: 18px; font-weight: 600; padding: 6px; }
            """
        )

        # Keyboard / menu shortcuts (optional)
        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_data)
        self.addAction(save_action)

    # ---------------------------
    # Data management
    # ---------------------------
    def _load_data(self):
        if not os.path.exists(DATA_FILE):
            self.lists = {}
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                self.lists = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Load Error",
                                f"Could not load data: {e}")
            self.lists = {}
        self._refresh_sidebar()

    def _save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.lists, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Saved", "All lists saved to disk.")
        except Exception as e:
            QMessageBox.warning(self, "Save Error",
                                f"Could not save data: {e}")

    def _refresh_sidebar(self):
        self.lists_widget.clear()
        for title in self.lists.keys():
            item = QListWidgetItem(title)
            self.lists_widget.addItem(item)

    # ---------------------------
    # List & task operations
    # ---------------------------
    def _create_list_dialog(self):
        title, ok = QInputDialogText.getText(self, "New List", "List title:")
        # Use small helper below because we avoid importing QInputDialog directly for clarity
        if ok and title:
            if title in self.lists:
                QMessageBox.information(
                    self, "Exists", "A list with that title already exists.")
                return
            self.lists[title] = {"tasks": [], "reminder": ""}
            self._refresh_sidebar()
            # Select new list
            items = self.lists_widget.findItems(
                title, Qt.MatchFlag.MatchExactly)
            if items:
                self.lists_widget.setCurrentItem(items[0])

    def _on_list_selected(self):
        item = self.lists_widget.currentItem()
        if not item:
            self.title_label.setText("Select or create a list")
            self.tasks_widget.clear()
            self.reminder_info.setText("")
            return
        title = item.text()
        self.title_label.setText(title)
        self.title_edit.setText(title)
        data = self.lists.get(title, {"tasks": [], "reminder": ""})
        self.tasks_widget.clear()
        for t in data.get("tasks", []):
            self.tasks_widget.addItem(t)
        # Show reminder if set
        rem = data.get("reminder", "")
        if rem:
            try:
                dtobj = dt.datetime.fromisoformat(rem)
                self.reminder_info.setText(
                    "Reminder: " + dtobj.strftime("%Y-%m-%d %H:%M"))
            except Exception:
                self.reminder_info.setText("Reminder: (invalid)")
        else:
            self.reminder_info.setText("No reminder set")

    def _add_task_to_current_list(self):
        item = self.lists_widget.currentItem()
        if not item:
            QMessageBox.information(
                self, "No List", "Please select a list first.")
            return
        text = self.task_input.text().strip()
        if not text:
            return
        title = item.text()
        self.lists[title]["tasks"].append(text)
        self.tasks_widget.addItem(text)
        self.task_input.clear()

    def _remove_selected_task(self):
        cur = self.tasks_widget.currentRow()
        if cur < 0:
            return
        item = self.lists_widget.currentItem()
        if not item:
            return
        title = item.text()
        removed = self.lists[title]["tasks"].pop(cur)
        self.tasks_widget.takeItem(cur)
        QMessageBox.information(self, "Removed", f"Removed: {removed}")

    def _delete_selected_list(self):
        item = self.lists_widget.currentItem()
        if not item:
            return
        title = item.text()
        confirm = QMessageBox.question(
            self, "Delete", f"Delete list '{title}'?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        # Remove scheduled job if exists
        rem = self.lists.get(title, {}).get("reminder", "")
        if rem:
            job_id = self._job_id_for(title)
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass
        self.lists.pop(title, None)
        self._refresh_sidebar()
        self.tasks_widget.clear()
        self.title_label.setText("Select or create a list")
        self.reminder_info.setText("")

    def _rename_current_list(self):
        item = self.lists_widget.currentItem()
        if not item:
            QMessageBox.information(
                self, "No List", "Select a list to rename.")
            return
        old_title = item.text()
        new_title = self.title_edit.text().strip()
        if not new_title:
            QMessageBox.information(self, "Empty", "Please enter a new title.")
            return
        if new_title == old_title:
            return
        if new_title in self.lists:
            QMessageBox.information(
                self, "Exists", "A list with that title already exists.")
            return
        self.lists[new_title] = self.lists.pop(old_title)
        # If there was a scheduled job under old id, re-register it with new id
        rem = self.lists[new_title].get("reminder", "")
        if rem:
            job_id_old = self._job_id_for(old_title)
            try:
                job = self.scheduler.get_job(job_id_old)
                if job:
                    # remove and re-add with new id
                    self.scheduler.remove_job(job_id_old)
                    run_dt = dt.datetime.fromisoformat(rem)
                    self._add_notification_job(new_title, run_dt)
            except Exception:
                pass
        self._refresh_sidebar()
        items = self.lists_widget.findItems(
            new_title, Qt.MatchFlag.MatchExactly)
        if items:
            self.lists_widget.setCurrentItem(items[0])

    # ---------------------------
    # Reminder scheduling
    # ---------------------------
    def _job_id_for(self, list_title: str) -> str:
        # Normalized unique job id
        return "reminder__" + list_title.replace(" ", "_")

    def _add_notification_job(self, list_title: str, run_dt: dt.datetime):
        job_id = self._job_id_for(list_title)
        # If job already exists, remove and replace
        try:
            existing = self.scheduler.get_job(job_id)
            if existing:
                self.scheduler.remove_job(job_id)
        except Exception:
            pass

        def notify():
            n = Notify()
            n.title = f"Reminder — {list_title}"
            tasks = self.lists.get(list_title, {}).get("tasks", [])
            n.message = (
                f"You scheduled a reminder for '{list_title}'.\nTasks:\n"
                + "\n".join(f"- {t}" for t in tasks[:10])
            )
            try:
                n.send()
            except Exception:
                # Silently ignore notifications failures (platform differences)
                pass
            # After firing, clear the saved reminder for the list
            if list_title in self.lists:
                self.lists[list_title]["reminder"] = ""
                # reflect in UI
                cur = self.lists_widget.currentItem()
                if cur and cur.text() == list_title:
                    self.reminder_info.setText("No reminder set")
                # Persist change
                self._save_data()

        try:
            # Use add_job with id to be able to remove/replace it later
            self.scheduler.add_job(notify, "date", run_date=run_dt, id=job_id)
        except ConflictingIdError:
            # If a job with same id exists, remove then add
            try:
                self.scheduler.remove_job(job_id)
                self.scheduler.add_job(
                    notify, "date", run_date=run_dt, id=job_id)
            except Exception:
                pass

    def _schedule_reminder_for_current_list(self):
        item = self.lists_widget.currentItem()
        if not item:
            QMessageBox.information(
                self, "No List", "Select a list to schedule a reminder.")
            return
        title = item.text()
        qdate = self.calendar.selectedDate()
        qtime = self.time_edit.time()
        run_dt = dt.datetime(qdate.year(), qdate.month(),
                             qdate.day(), qtime.hour(), qtime.minute(), 0)
        if run_dt <= dt.datetime.now():
            QMessageBox.information(
                self, "Invalid", "Please select a future date/time.")
            return
        # Save in model
        self.lists[title]["reminder"] = run_dt.isoformat()
        # Register job
        self._add_notification_job(title, run_dt)
        self.reminder_info.setText(
            "Reminder: " + run_dt.strftime("%Y-%m-%d %H:%M"))
        QMessageBox.information(
            self, "Scheduled", f"Reminder set for {title} at {run_dt}")

    def _clear_reminder_for_current_list(self):
        item = self.lists_widget.currentItem()
        if not item:
            return
        title = item.text()
        rem = self.lists[title].get("reminder", "")
        if not rem:
            QMessageBox.information(
                self, "No Reminder", "This list has no reminder.")
            return
        job_id = self._job_id_for(title)
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass
        self.lists[title]["reminder"] = ""
        self.reminder_info.setText("No reminder set")
        QMessageBox.information(self, "Cleared", "Reminder cleared.")

    def _schedule_existing_reminders(self):
        # Re-register reminders that are saved and in the future
        for title, data in self.lists.items():
            rem = data.get("reminder", "")
            if rem:
                try:
                    run_dt = dt.datetime.fromisoformat(rem)
                    if run_dt > dt.datetime.now():
                        self._add_notification_job(title, run_dt)
                    else:
                        # Past reminder: clear it
                        self.lists[title]["reminder"] = ""
                except Exception:
                    self.lists[title]["reminder"] = ""

    def _mark_list_done(self):
        item = self.lists_widget.currentItem()
        if not item:
            return
        title = item.text()
        # Simple UX: move tasks to "(done)" suffix and clear reminder
        self.lists[title]["tasks"] = [
            "✔ " + t for t in self.lists[title]["tasks"]]
        self.lists[title]["reminder"] = ""
        # remove scheduled job if any
        try:
            self.scheduler.remove_job(self._job_id_for(title))
        except Exception:
            pass
        self._on_list_selected()
        QMessageBox.information(
            self, "Done", f"Marked '{title}' as done (visual only).")


# Small helper input dialog that avoids importing QInputDialog everywhere
class QInputDialogText:
    @staticmethod
    def getText(parent, title, label):
        # Minimal custom dialog using QLineEdit and Buttons
        dlg = QMessageBox(parent)
        dlg.setWindowTitle(title)
        dlg.setText(label)
        dlg.setIcon(QMessageBox.Icon.Information)
        # Trick: we embed a QLineEdit in the message box's layout
        line = QLineEdit(dlg)
        line.setPlaceholderText("")
        layout = dlg.layout()
        layout.addWidget(line, 1, 1)
        ok = dlg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        dlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dlg.exec()
        if dlg.clickedButton() == ok:
            return line.text(), True
        return "", False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TodoApp()
    window.show()
    sys.exit(app.exec())

import sys
import re
import time
import threading
import os
import json
from datetime import datetime
from collections import deque

from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QTextBrowser, QTextEdit, QMessageBox, QHBoxLayout,
                               QProgressBar, QDialog, QDialogButtonBox,
                               QCheckBox, QComboBox, QSizePolicy)
from PySide6.QtCore import Qt, QSettings, Signal, Slot, QObject, QThread

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']


OAuth is here to put


    }
}
TOKEN_FILE = "token.json"
HISTORY_FILE = "copy_history.log"
BATCH_SIZE = 100

def color_text(text, color):
    return f'<span style="color:{color}">{text}</span>'

def extract_id(url):
    if not url: return None
    patterns = [r"/folders/([a-zA-Z0-9_-]{20,})", r"/d/([a-zA-Z0-9_-]{20,})", r"id=([a-zA-Z0-9_-]{20,})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: return match.group(1)
    return None

class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("היסטוריית העתקות")
        self.setMinimumSize(600, 500)
        self.main_app = parent
        layout = QVBoxLayout()
        
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.load_history()
        layout.addWidget(self.history_text)
        
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 העתק היסטוריה")
        btn_copy.clicked.connect(self.copy_history)
        btn_clear = QPushButton("🗑️ נקה היסטוריה")
        btn_clear.clicked.connect(self.clear_history)
        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_clear)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        self.history_text.setPlainText(content)
                    else:
                        self.history_text.setPlainText("קובץ ההיסטוריה ריק.")
            except Exception as e:
                self.history_text.setPlainText(f"שגיאה בטעינת ההיסטוריה: {e}")
        else:
            self.history_text.setPlainText("אין קובץ היסטוריה עדיין.\nהיסטוריה תתחיל להישמר לאחר ההעתקה הראשונה.")
    
    def copy_history(self):
        QApplication.clipboard().setText(self.history_text.toPlainText())
        QMessageBox.information(self, "הצלחה", "ההיסטוריה הועתקה ללוח.")
    
    def clear_history(self):
        if QMessageBox.question(self, "אישור מחיקה", "האם אתה בטוח שברצונך למחוק את כל ההיסטוריה?", 
                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.main_app.clear_history_file()
            self.history_text.clear()
            self.history_text.setPlainText("ההיסטוריה נמחקה.")

class InfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("מידע והיסטוריה")
        self.setFixedSize(450, 250)
        layout = QVBoxLayout()
        
        about_label = QLabel()
        about_label.setTextFormat(Qt.RichText)
        about_label.setOpenExternalLinks(True)
        about_label.setText("""
        <h3>🚀 כלי העתקת קבצים ותיקיות בגוגל דרייב</h3>
        <p><b>לפרופיל שלי במתמחים טופ:</b> <a href='https://mitmachim.top/user/%D7%90%D7%9C%D7%99%D7%94%D7%95-%D7%90.%D7%91'>לחץ כאן</a></p>
        <p>פותח על ידי: <b>אלי </b> | <b>eli@mkifnjv.click</b></p>
        <p>גירסה: 2.1 | עודכן: 2025</p>
        """)
        layout.addWidget(about_label)
        
        btn_history = QPushButton("📜 הצג היסטוריית העתקות")
        btn_history.clicked.connect(lambda: HistoryDialog(self.parent()).exec())
        layout.addWidget(btn_history)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
        self.setLayout(layout)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("הגדרות")
        self.setMinimumSize(450, 260)
        self.settings = parent.settings_manager
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🎨 ערכת נושא:"))
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["בהיר", "כהה"])
        self.theme_selector.setCurrentText(self.settings.value("theme", "בהיר"))
        layout.addWidget(self.theme_selector)
        
        self.rename_checkbox = QCheckBox("שנה שם בהעתקה (הוסף 'העתק')")
        self.rename_checkbox.setChecked(self.settings.value("rename_on_copy", True, type=bool))
        layout.addWidget(self.rename_checkbox)
        
        layout.addSpacing(15)
        layout.addWidget(QLabel("🎯 הדבק קישור ליעד:"))
        self.default_dest_url_input = QLineEdit()
        self.default_dest_url_input.setPlaceholderText("הדבק כאן קישור לתיקייה")
        self.default_dest_url_input.setText(self.settings.value("default_dest_url", ""))
        layout.addWidget(self.default_dest_url_input)
        
        self.btn_reset_connection = QPushButton("🔄 אפס חיבור לגוגל דרייב")
        self.btn_reset_connection.clicked.connect(self.reset_drive_connection)
        layout.addWidget(self.btn_reset_connection)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self.setLayout(layout)
    
    def reset_drive_connection(self):
        if os.path.exists(TOKEN_FILE):
            reply = QMessageBox.question(self, "אישור איפוס חיבור",
                "האם אתה בטוח שברצונך לאפס את החיבור לגוגל דרייב? זה ידרוש ממך להתחבר מחדש.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    os.remove(TOKEN_FILE)
                    QMessageBox.information(self, "הצלחה", "החיבור לגוגל דרייב אופס בהצלחה.")
                except Exception as e:
                    QMessageBox.warning(self, "שגיאה", f"לא ניתן למחוק את קובץ האימות: {e}")
        else:
            QMessageBox.information(self, "אין חיבור", "אין חיבור קיים לאיפוס.")
    
    def accept(self):
        self.settings.setValue("theme", self.theme_selector.currentText())
        self.settings.setValue("rename_on_copy", self.rename_checkbox.isChecked())
        
        url = self.default_dest_url_input.text().strip()
        if not url:
            self.settings.remove("default_dest_url")
            self.settings.remove("default_dest_id")
        else:
            folder_id = extract_id(url)
            if not folder_id:
                QMessageBox.warning(self, "שגיאה", "קישור ברירת המחדל אינו תקין.")
                return
            self.settings.setValue("default_dest_url", url)
            self.settings.setValue("default_dest_id", folder_id)
        super().accept()

class DriveCopierWorker(QObject):
    progress_updated = Signal(object, int, int, float, str)
    log_message = Signal(str, str)
    copy_finished = Signal(object, str, str, bool, str, str)
    
    def __init__(self, source_url, dest_folder_id, settings_manager):
        super().__init__()
        self.source_url = source_url
        self.dest_folder_id = dest_folder_id
        self.settings_manager = settings_manager
        self.creds = None
        self.service = None
        self.stop_requested = False
        self.source_name = self.source_url
        self.copy_context = {'total': 0, 'copied': 0, 'start_time': 0, 'lock': threading.Lock()}
        self.failed_items_during_copy = []
    
    def request_stop(self):
        self.stop_requested = True
        self.log_message.emit("⏹️ בקשת עצירה התקבלה... התהליך ייפסק בקרוב.", "red")
    
    @Slot()
    def run_copy_process(self):
        final_message, final_color, success_overall, new_item_id, item_type = "שגיאה", "red", False, None, None
        try:
            if not self.authenticate():
                final_message = "העתקה נכשלה: בעיית התחברות לגוגל דרייב."
                return
            
            source_id = extract_id(self.source_url)
            if not source_id:
                final_message = "העתקה נכשלה: קישור המקור אינו תקין או לא מזוהה."
                return
            
            try:
                meta = self.service.files().get(fileId=source_id, fields='id, name, mimeType, permissions').execute()
            except HttpError as e:
                if e.resp.status == 404:
                    final_message = "העתקה נכשלה: הקובץ או התיקייה לא נמצאו. ייתכן שהם נמחקו או שאין לך הרשאת גישה."
                elif e.resp.status == 403:
                    final_message = "העתקה נכשלה: אין לך הרשאה לגשת לקובץ או התיקייה. בדוק שהקישור משותף איתך."
                else:
                    final_message = f"שגיאת Google Drive: {e}"
                return
            
            self.source_name = meta.get('name', self.source_url)
            self.log_message.emit(f"✅ נמצא: '{self.source_name}'", "blue")
            
            try:
                dest_info = self.service.files().get(fileId=self.dest_folder_id, fields='id, name, mimeType').execute()
                if dest_info.get('mimeType') != 'application/vnd.google-apps.folder':
                    final_message = "העתקה נכשלה: היעד שצוין אינו תיקייה."
                    return
                self.log_message.emit(f"✅ תיקיית יעד מאומתת: '{dest_info.get('name')}'", "blue")
            except HttpError as e:
                if e.resp.status == 404:
                    final_message = "העתקה נכשלה: תיקיית היעד לא נמצאה."
                elif e.resp.status == 403:
                    final_message = "העתקה נכשלה: אין לך הרשאת כתיבה לתיקיית היעד."
                else:
                    final_message = f"שגיאה בגישה לתיקיית היעד: {e}"
                return
            
            is_folder = meta.get('mimeType') == 'application/vnd.google-apps.folder'
            item_type = 'folder' if is_folder else 'file'
            
            if is_folder:
                self.log_message.emit(f"📁 סופר קבצים בתוך התיקייה '{self.source_name}'...", "gray")
                total_files = self.count_files_in_folder(source_id)
                if total_files == -1:
                    final_message = "העתקה בוטלה במהלך ספירת קבצים."
                    return
                self.log_message.emit(f"📊 נמצאו {total_files} קבצים להעתקה.", "blue")
            else:
                total_files = 1
            
            self.copy_context['total'] = total_files
            self.copy_context['start_time'] = time.time()
            
            self.log_message.emit(f"🚀 מתחיל העתקה עבור '{self.source_name}'...", "gray")
            
            new_item_id = self.copy_item_recursive(source_id, self.dest_folder_id)
            
            if self.stop_requested:
                final_message = "⏹️ ההעתקה הופסקה על ידי המשתמש!"
            elif new_item_id:
                copied_count = self.copy_context['copied']
                if total_files == 0 and is_folder:
                    final_message = f"🎉 התיקייה הריקה '{self.source_name}' הועתקה בהצלחה!"
                else:
                    final_message = f"🎉 הושלם! {copied_count}/{total_files} קבצים הועתקו בהצלחה."
                success_overall, final_color = True, "green"
            else:
                final_message = "❌ ההעתקה נכשלה - לא ניתן היה ליצור העתק."
                
        except HttpError as e:
            final_message = f"❌ שגיאת Google Drive: {e}"
        except Exception as e:
            final_message = f"❌ שגיאה לא צפויה: {str(e)}"
        finally:
            self.copy_finished.emit(self, final_message, final_color, success_overall, new_item_id, item_type)
    
    def copy_item_recursive(self, item_id, dest_folder_id):
        if self.stop_requested:
            return None
        
        try:
            item_meta = self.service.files().get(fileId=item_id, fields='id, name, mimeType').execute()
            name = item_meta.get('name')
            is_folder = item_meta.get('mimeType') == 'application/vnd.google-apps.folder'
            rename_on_copy = self.settings_manager.value("rename_on_copy", True, type=bool)
            
            if is_folder:
                self.log_message.emit(f"📁 יוצר תיקייה: '{name}'", "purple")
                try:
                    new_folder = self.service.files().create(
                        body={
                            'name': name,
                            'mimeType': 'application/vnd.google-apps.folder',
                            'parents': [dest_folder_id]
                        },
                        fields='id'
                    ).execute()
                    new_folder_id = new_folder.get('id')
                    
                    all_children, page_token = [], None
                    while not self.stop_requested:
                        try:
                            response = self.service.files().list(
                                q=f"'{item_id}' in parents and trashed=false",
                                fields="nextPageToken, files(id, name, mimeType)",
                                pageToken=page_token,
                                pageSize=1000
                            ).execute()
                            all_children.extend(response.get('files', []))
                            page_token = response.get('nextPageToken')
                            if not page_token:
                                break
                        except HttpError as e:
                            self.log_message.emit(f"❌ שגיאה בקבלת רשימת קבצים: {e}", "red")
                            break
                    
                    files_to_copy = [c for c in all_children if c.get('mimeType') != 'application/vnd.google-apps.folder']
                    sub_folders = [c for c in all_children if c.get('mimeType') == 'application/vnd.google-apps.folder']
                    
                    for i in range(0, len(files_to_copy), BATCH_SIZE):
                        if self.stop_requested:
                            break
                        batch_chunk = files_to_copy[i:i + BATCH_SIZE]
                        self.log_message.emit(f"⚡️ מעתיק אצווה של {len(batch_chunk)} קבצים...", "darkcyan")
                        
                        batch = self.service.new_batch_http_request(callback=self.batch_callback)
                        for file in batch_chunk:
                            final_name = f"{file['name']} (העתק)" if rename_on_copy else file['name']
                            try:
                                batch.add(
                                    self.service.files().copy(
                                        fileId=file['id'],
                                        body={'name': final_name, 'parents': [new_folder_id]},
                                        fields='id'
                                    ),
                                    request_id=file['name']
                                )
                            except Exception as e:
                                self.log_message.emit(f"❌ שגיאה בהכנת העתקה לקובץ '{file['name']}': {e}", "red")
                                self.failed_items_during_copy.append(f"'{file['name']}' - {e}")
                        
                        try:
                            batch.execute()
                        except Exception as e:
                            self.log_message.emit(f"❌ שגיאה בביצוע אצווה: {e}", "red")
                            self.failed_items_during_copy.append(f"אצווה שלמה נכשלה - {e}")
                    
                    for folder in sub_folders:
                        if self.stop_requested:
                            break
                        self.copy_item_recursive(folder['id'], new_folder_id)
                    
                    return new_folder_id
                    
                except HttpError as e:
                    self.log_message.emit(f"❌ שגיאה ביצירת תיקייה '{name}': {e}", "red")
                    self.failed_items_during_copy.append(f"תיקייה '{name}' - {e}")
                    return None
            else:
                self.log_message.emit(f"📄 מעתיק קובץ: '{name}'", "purple")
                final_name = f"{name} (העתק)" if rename_on_copy else name
                try:
                    new_file = self.service.files().copy(
                        fileId=item_id,
                        body={'name': final_name, 'parents': [dest_folder_id]},
                        fields='id'
                    ).execute()
                    self.update_progress(1)
                    return new_file.get('id')
                except HttpError as e:
                    self.log_message.emit(f"❌ שגיאה בהעתקת קובץ '{name}': {e}", "red")
                    self.failed_items_during_copy.append(f"קובץ '{name}' - {e}")
                    return None
                    
        except Exception as e:
            item_name_for_log = item_meta.get('name', f"ID:{item_id}") if 'item_meta' in locals() else f"ID:{item_id}"
            self.log_message.emit(f"❌ שגיאה כללית בהעתקת '{item_name_for_log}': {e}", "red")
            self.failed_items_during_copy.append(f"'{item_name_for_log}' - {e}")
            return None
    
    def batch_callback(self, request_id, response, exception):
        if exception:
            self.log_message.emit(f"❌ שגיאה בהעתקת '{request_id}': {exception}", "red")
            self.failed_items_during_copy.append(f"'{request_id}' - {exception}")
        else:
            self.log_message.emit(f"✅ קובץ '{request_id}' הועתק בהצלחה באצווה.", "darkgreen")
        self.update_progress(1)
    
    def update_progress(self, count):
        with self.copy_context['lock']:
            self.copy_context['copied'] += count
            ctx = self.copy_context
            elapsed = time.time() - ctx['start_time']
            
            if elapsed > 1:
                speed = ctx['copied'] / elapsed
                eta_sec = (ctx['total'] - ctx['copied']) / speed if speed > 0 else 0
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
            else:
                speed, eta_str = 0, "מחשב..."
            
            self.progress_updated.emit(self, ctx['copied'], ctx['total'], speed, eta_str)
    
    def authenticate(self):
        creds = None
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception as e:
                self.log_message.emit(f"⚠️ שגיאה בטעינת אימות שמור: {e}", "red")
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    self.log_message.emit("🔄 מרענן אימות...", "blue")
                    creds.refresh(Request())
                except Exception as e:
                    self.log_message.emit(f"❌ כשל בריענון: {e}", "red")
                    creds = None
            
            if not creds or not creds.valid:
                try:
                    self.log_message.emit("🔑 מבצע אימות חדש...", "blue")
                    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    self.log_message.emit(f"❌ שגיאת אימות: {e}", "red")
                    return False
            
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                self.log_message.emit(f"⚠️ שגיאה בשמירת אימות: {e}", "orange")
        
        self.creds = creds
        try:
            self.service = build('drive', 'v3', credentials=self.creds)
            self.log_message.emit("🔐 התחברות לגוגל דרייב הצליחה.", "green")
            return True
        except Exception as e:
            self.log_message.emit(f"❌ שגיאה בבניית שירות דרייב: {e}", "red")
            return False
    
    def count_files_in_folder(self, folder_id):
        count = 0
        folders_to_scan = deque([folder_id])
        
        while folders_to_scan:
            if self.stop_requested:
                return -1
            
            current_folder_id = folders_to_scan.popleft()
            page_token = None
            
            try:
                while True:
                    if self.stop_requested:
                        return -1
                    
                    response = self.service.files().list(
                        q=f"'{current_folder_id}' in parents and trashed=false",
                        fields="nextPageToken, files(id, mimeType)",
                        pageToken=page_token,
                        pageSize=1000
                    ).execute()
                    
                    for item in response.get('files', []):
                        if item.get('mimeType') == 'application/vnd.google-apps.folder':
                            folders_to_scan.append(item['id'])
                        else:
                            count += 1
                    
                    page_token = response.get('nextPageToken')
                    if not page_token:
                        break
                        
            except HttpError as e:
                self.log_message.emit(f"❌ שגיאה בספירת קבצים: {e}", "red")
                return -1
        
        return count


class DriveCopierApp(QWidget):
    MAX_SOURCE_INPUTS = 5
    MAX_CONCURRENT_WORKERS = 3
    
    def __init__(self):
        super().__init__()
        self.copy_queue = deque()
        self.active_workers = {}
        self.task_management_lock = threading.Lock()
        self.is_stopping = False
        self.settings_manager = QSettings("EliMKif", "DriveCopier")
        self.load_settings()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("CopyDrive - Eli")
        self.setMinimumSize(700, 650)
        main_layout = QVBoxLayout()
        
        top_bar_layout = QHBoxLayout()
        btn_info = QPushButton("ℹ️ מידע והיסטוריה")
        btn_info.clicked.connect(self.show_info_dialog)
        btn_settings = QPushButton("⚙️ הגדרות")
        btn_settings.clicked.connect(self.show_settings_dialog)
        top_bar_layout.addWidget(btn_info)
        top_bar_layout.addWidget(btn_settings)
        top_bar_layout.addStretch()
        
        self.btn_clear_log = QPushButton("🧹 נקה יומן")
        self.btn_clear_log.setToolTip("נקה את תצוגת היומן הנוכחית")
        self.btn_clear_log.clicked.connect(self.clear_log_display)
        top_bar_layout.addWidget(self.btn_clear_log)
        
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(35, 35)
        self.btn_refresh.setObjectName("refreshButton")
        self.btn_refresh.setToolTip("נקה שדות והתחל מחדש")
        self.btn_refresh.clicked.connect(self.reset_ui)
        top_bar_layout.addWidget(self.btn_refresh)
        
        main_layout.addLayout(top_bar_layout)
        
        title = QLabel("🚀 CopyDrive 🚀")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title)
        
        main_layout.addWidget(QLabel("🔗 הדבק קישור למקור (אחד או יותר):"))
        self.source_inputs_layout = QVBoxLayout()
        self.source_input_widgets = []
        self.add_source_input()
        main_layout.addLayout(self.source_inputs_layout)
        
        # שדה יעד
        main_layout.addWidget(QLabel("🎯 הדבק קישור ליעד:"))
        self.input_dest_folder = QLineEdit()
        self.input_dest_folder.setMinimumHeight(35)
        main_layout.addWidget(self.input_dest_folder)
        
        self.btn_action = QPushButton("📋 התחל העתקה")
        self.btn_action.setObjectName("actionButton")
        self.btn_action.setCheckable(True)
        self.btn_action.clicked.connect(self.toggle_copy_process)
        main_layout.addWidget(self.btn_action)
        
        self.log_output = QTextBrowser()
        self.log_output.setOpenExternalLinks(True)
        main_layout.addWidget(self.log_output)
        
        self.progress_layout = QVBoxLayout()
        main_layout.addLayout(self.progress_layout)
        
        self.status_label = QLabel("סטטוס: מוכן")
        main_layout.addWidget(self.status_label)
        
        credit_label = QLabel("פותח על ידי אלי  | eli@mkifnjv.click")
        credit_label.setAlignment(Qt.AlignCenter)
        credit_label.setStyleSheet("font-size: 10px; color: grey;")
        main_layout.addWidget(credit_label)
        
        self.setLayout(main_layout)
        self.reset_ui()
    
    @Slot()
    def clear_log_display(self):
        self.log_output.clear()
        self._log_to_ui("--- היומן נוקה ---", "gray")
    
    def toggle_copy_process(self):
        if self.btn_action.isChecked():
            self.start_copy_operation()
        else:
            self.request_stop_all_operations()
    
    def start_copy_operation(self):
        self.is_stopping = False
        self.log_output.clear()
        
        source_urls = [w[0].text().strip() for w in self.source_input_widgets if w[0].text().strip()]
        if not source_urls:
            QMessageBox.warning(self, "שגיאה", "יש להזין לפחות קישור מקור אחד.")
            self.update_action_button_state(False)
            return
        
        dest_url = self.input_dest_folder.text().strip()
        dest_id = extract_id(dest_url)
        if not dest_id:
            self.load_settings()
            if not self.default_dest_folder_id:
                QMessageBox.warning(self, "שגיאה", "יש להזין קישור יעד תקין או להגדיר ברירת מחדל בהגדרות.")
                self.update_action_button_state(False)
                return
            dest_id = self.default_dest_folder_id
            self._log_to_ui("ℹ️ שימוש ביעד ברירת המחדל.", "blue")
        
        with self.task_management_lock:
            self.copy_queue.clear()
            self.active_workers.clear()
            for url in source_urls:
                self.copy_queue.append((url, dest_id))
        
        self.update_action_button_state(is_copying=True)
        self._log_to_ui(f"🚀 התחלת עיבוד של {len(source_urls)} משימות...", "navy")
        self.status_label.setText(f"סטטוס: מכין {len(source_urls)} העתקות...")
        
        for _ in range(self.MAX_CONCURRENT_WORKERS):
            self._launch_next_worker()
    
    def _launch_next_worker(self):
        if self.is_stopping:
            return
        
        with self.task_management_lock:
            if self.copy_queue and len(self.active_workers) < self.MAX_CONCURRENT_WORKERS:
                source_url, dest_id = self.copy_queue.popleft()
                
                progress_bar = QProgressBar()
                progress_bar.setValue(0)
                progress_bar.setFormat(f"ממתין להתחלה... ({source_url[:30]}...) - %p%")
                self.progress_layout.addWidget(progress_bar)
                
                worker = DriveCopierWorker(source_url, dest_id, self.settings_manager)
                thread = QThread()
                worker.moveToThread(thread)
                worker.progress_bar = progress_bar
                
                thread.started.connect(worker.run_copy_process)
                worker.progress_updated.connect(self.update_status_display)
                worker.log_message.connect(self._log_to_ui)
                worker.copy_finished.connect(self.handle_worker_completion)
                
                self.active_workers[worker] = thread
                thread.start()
                self._log_to_ui(f"🚀 משימה הופעלה עבור: {source_url}", "darkblue")
    
    @Slot(object, int, int, float, str)
    def update_status_display(self, worker, copied, total, speed, eta_str):
        with self.task_management_lock:
            if worker in self.active_workers and hasattr(worker, 'progress_bar'):
                progress = int((copied / total) * 100) if total > 0 else 0
                worker.progress_bar.setValue(progress)
                worker.progress_bar.setFormat(f"{worker.source_name}: {copied}/{total} ({speed:.1f} קבצים/ש') | נותר: {eta_str} - %p%")
        
        total_active = len(self.active_workers)
        total_queued = len(self.copy_queue)
        self.status_label.setText(f"סטטוס: {total_active} העתקות פעילות, {total_queued} ממתינות בתור.")
    
    @Slot(object, str, str, bool, str, str)
    def handle_worker_completion(self, worker, message, color, success, new_item_id, item_type):
        self._log_to_ui(f"--- סיום משימה עבור '{worker.source_name}' ---", "navy")
        
        if success and new_item_id:
            drive_url = f"https://drive.google.com/drive/folders/{new_item_id}" if item_type == 'folder' else f"https://drive.google.com/file/d/{new_item_id}"
            self._log_to_ui(f"✅ {message} <a href='{drive_url}'>🔗 לחץ לצפייה בדרייב</a>", "green")
        else:
            self._log_to_ui(f"❌ {message}", color)
        
        if worker.failed_items_during_copy:
            failed_count = len(worker.failed_items_during_copy)
            self._log_to_ui(f"⚠️ {failed_count} פריטים נכשלו בהעתקת '{worker.source_name}':", "orange")
            for item in worker.failed_items_during_copy[:5]:  
                self._log_to_ui(f"  - {item}", "orange")
            if failed_count > 5:
                self._log_to_ui(f"  ... ועוד {failed_count - 5} פריטים.", "orange")
        
        self.save_history_entry(worker.source_url, worker.source_name, message, success, new_item_id, item_type)
        
        with self.task_management_lock:
            if worker in self.active_workers:
                thread = self.active_workers.pop(worker)
                thread.quit()
                thread.wait(250)
                
                if hasattr(worker, 'progress_bar'):
                    if success:
                        worker.progress_bar.setFormat(f"✅ הושלם - {worker.source_name}")
                        worker.progress_bar.setValue(100)
                    else:
                        worker.progress_bar.setFormat(f"❌ נכשל - {worker.source_name}")
                        worker.progress_bar.setValue(0)
                
                worker.deleteLater()
                thread.deleteLater()
        
        self._launch_next_worker()
        
        with self.task_management_lock:
            if not self.copy_queue and not self.active_workers:
                self._finish_all_copies()
    
    def _finish_all_copies(self):
        self._log_to_ui("\n🎉 --- כל משימות ההעתקה הושלמו! ---", "darkgreen")
        self.status_label.setText("סטטוס: כל ההעתקות הושלמו. מוכן לפעולה הבאה.")
        self.update_action_button_state(is_copying=False)
    
    def request_stop_all_operations(self):
        self.is_stopping = True
        with self.task_management_lock:
            self.copy_queue.clear()
            for worker in self.active_workers.keys():
                worker.request_stop()
        self._log_to_ui("⏹️ בקשת עצירה לכל המשימות התקבלה...", "red")
    
    def closeEvent(self, event):
        self.request_stop_all_operations()
        time.sleep(0.5)
        event.accept()
    
    def add_source_input(self):
        if len(self.source_input_widgets) >= self.MAX_SOURCE_INPUTS:
            return
        
        new_input = QLineEdit()
        new_input.setPlaceholderText("https://drive.google.com/...")
        new_input.setMinimumHeight(35)
        
        btn = QPushButton()
        btn.setFixedSize(30, 30)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        row_layout = QHBoxLayout()
        row_layout.addWidget(new_input)
        row_layout.addWidget(btn)
        
        self.source_inputs_layout.addLayout(row_layout)
        self.source_input_widgets.append((new_input, btn, row_layout))
        self._update_source_buttons()
    
    def remove_source_input(self, input_line_to_remove):
        for i, (input_line, btn, row_layout) in enumerate(self.source_input_widgets):
            if input_line == input_line_to_remove:
                row_layout.removeWidget(input_line)
                row_layout.removeWidget(btn)
                input_line.deleteLater()
                btn.deleteLater()
                self.source_inputs_layout.removeItem(row_layout)
                row_layout.deleteLater()
                del self.source_input_widgets[i]
                break
        self._update_source_buttons()
    
    def _update_source_buttons(self):
        for i, (input_line, btn, row_layout) in enumerate(self.source_input_widgets):
            try:
                btn.clicked.disconnect()
            except RuntimeError:
                pass
            
            if i == len(self.source_input_widgets) - 1:
                btn.setText("+")
                btn.clicked.connect(self.add_source_input)
                btn.setEnabled(len(self.source_input_widgets) < self.MAX_SOURCE_INPUTS)
            else:
                btn.setText("-")
                btn.clicked.connect(lambda checked=False, line=input_line: self.remove_source_input(line))
                btn.setEnabled(True)
    
    def reset_ui(self):
        self.request_stop_all_operations()
        time.sleep(0.1)
        
        while len(self.source_input_widgets) > 1:
            self.remove_source_input(self.source_input_widgets[-1][0])
        if self.source_input_widgets:
            self.source_input_widgets[0][0].clear()
        
        self.input_dest_folder.setText(self.default_dest_folder_url)
        
        self.log_output.clear()
        for i in reversed(range(self.progress_layout.count())):
            widget = self.progress_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        
        self.status_label.setText("סטטוס: מוכן")
        self.update_action_button_state(is_copying=False)
        self.apply_theme()
        
        with self.task_management_lock:
            self.copy_queue.clear()
            self.active_workers.clear()
        
        self._update_source_buttons()
    
    def show_info_dialog(self):
        InfoDialog(self).exec()
    
    def show_settings_dialog(self):
        if SettingsDialog(self).exec():
            self.load_settings()
            self.input_dest_folder.setText(self.default_dest_folder_url)
            self.apply_theme()
            self._log_to_ui("⚙️ הגדרות עודכנו.", "blue")
    
    def clear_history_file(self):
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
            self._log_to_ui("🗑️ קובץ ההיסטוריה נמחק.", "blue")
    
    @Slot(str, str)
    def _log_to_ui(self, text, color="black"):
        self.log_output.append(color_text(text, color))
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
    
    def update_action_button_state(self, is_copying):
        self.btn_action.setChecked(is_copying)
        
        if is_copying:
            self.btn_action.setText("⏹️ עצור הכל")
            for line_edit, button, _ in self.source_input_widgets:
                line_edit.setEnabled(False)
                button.setEnabled(False)
            self.input_dest_folder.setEnabled(False)
            self.btn_refresh.setEnabled(False)
        else:
            self.btn_action.setText("📋 התחל העתקה")
            for line_edit, _, _ in self.source_input_widgets:
                line_edit.setEnabled(True)
            self._update_source_buttons()
            self.input_dest_folder.setEnabled(True)
            self.btn_refresh.setEnabled(True)
        
        self.apply_theme()
    
    def apply_theme(self):
        theme = self.settings_manager.value("theme", "בהיר")
        base_style = ""
        
        if theme == "כהה":
            base_style = """
            QWidget { 
                background-color: #2c3e50; 
                color: #ecf0f1; 
            }
            QPushButton { 
                background-color: #34495e; 
                color: #ecf0f1; 
                border-radius: 5px; 
                padding: 6px; 
            }
            QPushButton:hover {
                background-color: #4a6741;
            }
            QLineEdit, QTextBrowser, QTextEdit, QComboBox { 
                background-color: #34495e; 
                color: #ecf0f1; 
                border: 1px solid #7f8c8d; 
                border-radius: 3px;
                padding: 4px;
            }
            QProgressBar { 
                border: 1px solid #7f8c8d; 
                text-align: center; 
                color: #ecf0f1; 
                background-color: #34495e;
                border-radius: 3px;
            }
            QProgressBar::chunk { 
                background-color: #27ae60; 
                border-radius: 2px;
            }
            QLabel { 
                color: #ecf0f1; 
            }
            """
        else:
            base_style = """
            QWidget { 
                background-color: #f0f0f0; 
                color: #333333; 
            }
            QPushButton { 
                background-color: #e0e0e0; 
                color: #333333; 
                border-radius: 5px; 
                padding: 6px; 
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QLineEdit, QTextBrowser, QTextEdit, QComboBox { 
                background-color: #ffffff; 
                color: #333333; 
                border: 1px solid #cccccc; 
                border-radius: 3px;
                padding: 4px;
            }
            QProgressBar { 
                border: 1px solid #cccccc; 
                text-align: center; 
                color: #333; 
                background-color: #e0e0e0;
                border-radius: 3px;
            }
            QProgressBar::chunk { 
                background-color: #4CAF50; 
                border-radius: 2px;
            }
            QLabel { 
                color: #333333; 
            }
            """
        
        action_button_style = """
        QPushButton#actionButton { 
            padding: 12px; 
            font-size: 16px; 
            font-weight: bold; 
        """
        if self.btn_action.isChecked():
            action_button_style += "background-color: #c0392b; color: white; }"
        else:
            action_button_style += "background-color: #27ae60; color: white; }"
        
        refresh_style = """
        QPushButton#refreshButton { 
            font-size: 16px; 
            border-radius: 17px; 
        }
        """
        
        self.setStyleSheet(base_style + action_button_style + refresh_style)
    
    def load_settings(self):
        self.rename_on_copy = self.settings_manager.value("rename_on_copy", True, type=bool)
        self.default_dest_folder_id = self.settings_manager.value("default_dest_id", None)
        self.default_dest_folder_url = self.settings_manager.value("default_dest_url", "")
    
    def save_history_entry(self, source_url, source_name, message, success, new_item_id=None, item_type=None):
        clean_message = re.sub(r'<[^>]+>', '', message).strip()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = "✅ הצליח" if success else "❌ נכשל"
        
        entry_lines = [
            f"[{timestamp}] {status}",
            f"📁 שם: {source_name}",
            f"🔗 מקור: {source_url}",
            f"📝 תוצאה: {clean_message}"
        ]
        
        if success and new_item_id:
            if item_type == 'folder':
                drive_url = f"https://drive.google.com/drive/folders/{new_item_id}"
            else:
                drive_url = f"https://drive.google.com/file/d/{new_item_id}"
            entry_lines.append(f"🎯 קישור: {drive_url}")
        
        entry = "\n".join(entry_lines) + "\n" + "-" * 50 + "\n\n"
        
        try:
            with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
                f.write(entry)
        except IOError as e:
            self._log_to_ui(f"⚠️ שגיאה בכתיבת היסטוריה: {e}", "red")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DriveCopierApp()
    window.show()
    sys.exit(app.exec())

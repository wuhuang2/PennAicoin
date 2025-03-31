import sys
import platform
import time
import sqlite3
import getpass
import vosk
import pyaudio
import json
import wave
import jieba
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView, QSizePolicy, QTextEdit, QListWidget, QListWidgetItem, QStackedWidget, QColorDialog, QGroupBox
)
from PyQt5.QtCore import QDate, Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap

from PyQt5.QtWidgets import QGroupBox  

class VoiceRecognition(QThread):
    recognized_text = pyqtSignal(str)
    recording_stopped = pyqtSignal()

    def __init__(self, model_path, timeout=20):
        super().__init__()
        self.model_path = model_path
        self.is_recording = False
        self.frames = []
        self.start_time = 0
        self.timeout = timeout
        self.recognizer = None
        self.p = None
        self.stream = None

    def run(self):
        try:
            print("正在加载语音识别模型...")
            self.recognizer = vosk.KaldiRecognizer(vosk.Model(self.model_path), 16000)
            self.p = pyaudio.PyAudio()
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024
            )
            print("模型加载成功，开始录音...")
            self.is_recording = True
            self.frames = []
            self.start_time = time.time()
            while self.is_recording:
                try:
                    data = self.stream.read(1024)
                except IOError as e:
                    print(f"音频流读取错误: {e}")
                    break
                self.frames.append(data)
                elapsed_time = time.time() - self.start_time
                if elapsed_time >= self.timeout:
                    print(f"录音超时，自动停止...（已录音 {elapsed_time:.1f} 秒）")
                    self.is_recording = False
                    self.recognized_text.emit("")
                    break
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")
                    if text:
                        self.recognized_text.emit(text)
            print("语音识别结束，处理识别结果...")
            result = json.loads(self.recognizer.FinalResult())
            recognized_text = result.get("text", "")
            self.recognized_text.emit(recognized_text)
            self.stop_recording()
            self.recording_stopped.emit()
        except Exception as e:
            print("语音识别线程出错:", e)
            self.recording_stopped.emit()

    def stop_recording(self):
        try:
            self.is_recording = False
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.p:
                self.p.terminate()
            print("音频资源已释放")
        except Exception as e:
            print("停止录音时出错:", e)

    def save_audio(self, filename):
        print(f"保存音频到文件: {filename}")
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b"".join(self.frames))


class AccountingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_db()
        self.voice_thread = None
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_time)
        self.update_timer.start(1000)

    def init_ui(self):
        self.setWindowTitle('记账本程序')
        self.setGeometry(100, 100, 1200, 800)

        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                color: #333333;
            }
            QLabel {
                line-height: 1.5;
            }
            QPushButton {
                border: 2px solid #8f8f91;
                border-radius: 6px;
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                  stop: 0 #f6f7fa, stop: 1 #dadbde);
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 14px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2c3e50;
            }
            QLineEdit, QDateEdit {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
            }
            QComboBox {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #cccccc;
                selection-background-color: #3498db;
                selection-color: #ffffff;
            }
            QTableWidget {
                background-color: #ffffff;
                color: #333333;
                gridline-color: #cccccc;
                border: 1px solid #cccccc;
                selection-background-color: #3498db;
                selection-color: #ffffff;
                font-size: 14px;
            }
            QHeaderView::section {
                background-color: #3498db;
                color: #ffffff;
                padding: 10px;
                border: 1px solid #2980b9;
                font-size: 14px;
            }
            QMessageBox {
                background-color: #f0f0f0;
                color: #333333;
            }
        """)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignCenter)
        font = self.time_label.font()
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setMinimumHeight(30)

        self.tool_bar = QToolBar(self)
        self.addToolBar(self.tool_bar)

        self.current_user = getpass.getuser()

        self.side_bar = QVBoxLayout()
        self.side_bar.setAlignment(Qt.AlignTop)
        self.side_bar.setSpacing(5)

        user_info_layout = QHBoxLayout()
        user_avatar_label = QLabel()
        user_avatar_label.setPixmap(QPixmap('user_icon.png').scaled(40, 40, Qt.IgnoreAspectRatio))
        user_info_layout.addWidget(user_avatar_label)
        user_label = QLabel(f"本地用户: {self.current_user}")
        user_info_layout.addWidget(user_label)
        user_info_layout.addStretch()
        self.side_bar.addLayout(user_info_layout)

        button_layout = QVBoxLayout()

        self.add_button = QPushButton('Add-添加')
        self.add_button.setIcon(QIcon('add_icon.png'))
        self.add_button.setFixedHeight(35)
        self.add_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_button.clicked.connect(self.show_add_dialog)
        button_layout.addWidget(self.add_button)

        self.delete_button = QPushButton('Delete-删除')
        self.delete_button.setIcon(QIcon('delete_icon.png'))
        self.delete_button.setFixedHeight(35)
        self.delete_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_record)
        button_layout.addWidget(self.delete_button)

        self.modify_button = QPushButton('Write-修改')
        self.modify_button.setIcon(QIcon('Write_icon.png'))
        self.modify_button.setFixedHeight(35)
        self.modify_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.modify_button.clicked.connect(self.modify_record)
        button_layout.addWidget(self.modify_button)

        self.export_button = QPushButton('Export-导出')
        self.export_button.setIcon(QIcon('Export_icon.png'))
        self.export_button.setFixedHeight(35)
        self.export_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.export_button.clicked.connect(self.show_export_prompt)
        button_layout.addWidget(self.export_button)

        self.import_button = QPushButton('Import-导入')
        self.import_button.setIcon(QIcon('Import_icon.png'))
        self.import_button.setFixedHeight(35)
        self.import_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_button.clicked.connect(self.show_import_prompt)
        button_layout.addWidget(self.import_button)

        self.settings_button = QPushButton('Settings-设置')
        self.settings_button.setIcon(QIcon('settings_icon.png'))
        self.settings_button.setFixedHeight(35)
        self.settings_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        button_layout.addWidget(self.settings_button)

        self.about_button = QPushButton('About-关于')
        self.about_button.setIcon(QIcon('about_icon.png'))
        self.about_button.setFixedHeight(35)
        self.about_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.about_button.clicked.connect(self.show_about_info)
        button_layout.addWidget(self.about_button)

        self.voice_button = QPushButton('🎤 开始录音')
        self.voice_button.setFixedHeight(35)
        self.voice_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_button.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.voice_button)

        self.recognition_display = QTextEdit()
        self.recognition_display.setReadOnly(True)
        self.recognition_display.setMaximumHeight(100)
        button_layout.addWidget(self.recognition_display)

        self.side_bar.addLayout(button_layout)

        robot_layout = QHBoxLayout()
        robot_label = QLabel()
        robot_label.setPixmap(QPixmap('robot_icon.png').scaled(200, 125, Qt.IgnoreAspectRatio))
        robot_layout.addWidget(robot_label)
        self.side_bar.addLayout(robot_layout)

        bottom_info_layout = QHBoxLayout()
        self.bottom_info = QLabel()
        bottom_info_layout.addWidget(self.bottom_info)
        self.side_bar.addLayout(bottom_info_layout)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.addWidget(self.time_label)

        side_and_table_layout = QHBoxLayout()
        self.side_bar_widget = QWidget()
        self.side_bar_widget.setLayout(self.side_bar)
        self.side_bar_widget.setFixedWidth(200)
        side_and_table_layout.addWidget(self.side_bar_widget)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["日期", "金额", "币种", "收支类型", "详细分类", "备注信息"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        side_and_table_layout.addWidget(self.table, 1)
        self.main_layout.addLayout(side_and_table_layout)

        copyright_layout = QHBoxLayout()
        copyright_label = QLabel("Copyright 2025 长治市屯留区机器人社团 饶晨曦 All Rights Reserved.\n 为参加第二十届宋庆龄少年儿童发明奖人工智能（编程）作品而开发。")
        copyright_layout.addWidget(copyright_label)
        copyright_layout.addStretch()
        self.main_layout.addLayout(copyright_layout)

        self.update_bottom_info()
        self.update_time()

    def init_db(self):
        self.conn = sqlite3.connect('accounting.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                amount REAL,
                currency TEXT,
                type TEXT,
                category TEXT,
                note TEXT
            )
        ''')
        self.conn.commit()

    def load_records(self):
        self.cursor.execute("SELECT * FROM records")
        records = self.cursor.fetchall()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.table.setItem(row, 5, QTableWidgetItem(record[6]))

    def toggle_recording(self):
        try:
            if self.voice_thread and self.voice_thread.isRunning():
                self.stop_recording()
            else:
                self.start_recording()
        except Exception as e:
            print("切换录音状态时出错:", e)

    def start_recording(self):
        try:
            self.voice_button.setText('🎤 结束录音')
            model_path = "./vosk-model-small-cn-0.22"
            timeout = 20
            self.voice_thread = VoiceRecognition(model_path, timeout)
            self.voice_thread.recognized_text.connect(self.process_voice_input)
            self.voice_thread.recording_stopped.connect(self.handle_recording_stopped)
            self.voice_thread.start()
            QMessageBox.information(None, "开始录音", "录音已开始...")
        except Exception as e:
            print("开始录音时出错:", e)

    def stop_recording(self):
        try:
            self.voice_button.setText('🎤 开始录音')
            if self.voice_thread and self.voice_thread.isRunning():
                self.voice_thread.is_recording = False
                self.voice_thread.quit()
                self.voice_thread.wait()
        except Exception as e:
            print("停止录音时出错:", e)

    def handle_recording_stopped(self):
        try:
            self.voice_button.setText('🎤 开始录音')
            QMessageBox.information(None, "停止录音", "录音已停止...")
        except Exception as e:
            print("处理录音停止信号时出错:", e)

    def process_voice_input(self, recognized_text):
        print("处理语音输入...")
        if recognized_text:
            print("识别到的语音:", recognized_text)
            words = jieba.lcut(recognized_text)
            date = self.extract_date(words)
            amount = self.extract_amount(words)
            currency = self.extract_currency(words)
            type_ = self.extract_type(words)
            category = self.extract_category(words)
            note = self.extract_note(words)

            self.recognition_display.append(recognized_text)

            self.add_record(date, amount, currency, type_, category, note)
        else:
            print("语音识别超时，未获取到有效内容")
            QMessageBox.warning(None, "语音识别超时", "语音识别超时，未获取到有效内容...")

    def extract_date(self, words):
        date_pattern = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日')
        for word in words:
            if date_pattern.match(word):
                return word.replace('年', '-').replace('月', '-').replace('日', '')
        return QDate.currentDate().toString("yyyy-MM-dd")

    def extract_amount(self, words):
        amount_pattern = re.compile(r'\d+\.?\d*')
        for word in words:
            match = amount_pattern.findall(word)
            if match:
                return float(match[0])
        return 0.0

    def extract_currency(self, words):
        currency_map = {
            '人民币': '人民币 (CNY)',
            '美元': '美元 (USD)',
            '欧元': '欧元 (EUR)',
            '日元': '日元 (JPY)'
        }
        for word in words:
            if word in currency_map:
                return currency_map[word]
        return '人民币 (CNY)'

    def extract_type(self, words):
        if '收入' in words:
            return '收入'
        elif '支出' in words:
            return '支出'
        else:
            return '支出'

    def extract_category(self, words):
        category_map = {
            '工资': '工资收入',
            '奖金': '奖金收入',
            '投资': '投资收益',
            '兼职': '兼职收入',
            '餐饮': '餐饮',
            '购物': '购物',
            '交通': '交通',
            '住房': '住房',
            '娱乐': '娱乐',
            '医疗': '医疗'
        }
        for word in words:
            if word in category_map:
                return category_map[word]
        return '其他'

    def extract_note(self, words):
        return ' '.join(words)

    def add_record(self, date, amount, currency, type_, category, note):
        print("添加记录到数据库...")
        try:
            self.cursor.execute("INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
                                (date, amount, currency, type_, category, note))
            self.conn.commit()
            self.load_records()
        except Exception as e:
            print(f"添加记录时出错: {str(e)}")

    def show_add_dialog(self):
        try:
            add_dialog = QDialog(self)
            add_dialog.setWindowTitle('添加账本')
            add_layout = QVBoxLayout()

            date_layout = QHBoxLayout()
            date_label = QLabel("日期:")
            date_input = QDateEdit()
            date_input.setDate(QDate.currentDate())
            date_input.setDisplayFormat("yyyy-MM-dd")
            date_layout.addWidget(date_label)
            date_layout.addWidget(date_input)

            amount_layout = QHBoxLayout()
            amount_label = QLabel("金额:")
            amount_input = QLineEdit()
            amount_layout.addWidget(amount_label)
            amount_layout.addWidget(amount_input)

            currency_layout = QHBoxLayout()
            currency_label = QLabel("币种:")
            currency_combobox = QComboBox()
            currency_combobox.addItems(["人民币 (CNY)", "美元 (USD)", "欧元 (EUR)", "日元 (JPY)", "其他"])
            currency_layout.addWidget(currency_label)
            currency_layout.addWidget(currency_combobox)

            type_layout = QHBoxLayout()
            type_label = QLabel("收支类型:")
            type_combobox = QComboBox()
            type_combobox.addItems(["收入", "支出"])
            type_layout.addWidget(type_label)
            type_layout.addWidget(type_combobox)

            category_layout = QHBoxLayout()
            category_label = QLabel("详细分类:")
            category_combobox = QComboBox()
            income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
            expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
            category_combobox.addItems(income_categories + expense_categories)
            category_layout.addWidget(category_label)
            category_layout.addWidget(category_combobox)

            note_layout = QHBoxLayout()
            note_label = QLabel("备注信息:")
            note_input = QLineEdit()
            note_layout.addWidget(note_label)
            note_layout.addWidget(note_input)

            button_layout = QHBoxLayout()
            add_button = QPushButton("添加记录")
            add_button.clicked.connect(lambda: self.add_new_record(
                date_input.date().toString("yyyy-MM-dd"),
                amount_input.text(),
                currency_combobox.currentText(),
                type_combobox.currentText(),
                category_combobox.currentText(),
                note_input.text(),
                add_dialog
            ))
            button_layout.addWidget(add_button)

            add_layout.addLayout(date_layout)
            add_layout.addLayout(amount_layout)
            add_layout.addLayout(currency_layout)
            add_layout.addLayout(type_layout)
            add_layout.addLayout(category_layout)
            add_layout.addLayout(note_layout)
            add_layout.addLayout(button_layout)

            add_dialog.setLayout(add_layout)
            add_dialog.exec_()
        except Exception as e:
            print(f"显示添加账本对话框时出错: {str(e)}")

    def add_new_record(self, date, amount_str, currency, type_, category, note, dialog):
        try:
            amount = float(amount_str)
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return

        self.cursor.execute("INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
                            (date, amount, currency, type_, category, note))
        self.conn.commit()
        self.load_records()
        dialog.close()

    def delete_record(self):
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return

        item = self.table.item(selected_row, 0)
        if item is None:
            QMessageBox.warning(self, "错误", "无法获取记录的 ID！")
            return
        record_id = item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.cursor.execute("DELETE FROM records WHERE id=?", (record_id,))
            self.conn.commit()
            self.load_records()

    def modify_record(self):
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return

        item = self.table.item(selected_row, 0)
        if item is None:
            QMessageBox.warning(self, "错误", "无法获取记录的 ID！")
            return
        record_id = item.data(Qt.UserRole)

        modify_dialog = QDialog(self)
        modify_dialog.setWindowTitle('修改记录')
        modify_layout = QVBoxLayout()

        date_layout = QHBoxLayout()
        date_label = QLabel("日期:")
        date_input = QDateEdit()
        date_input.setDate(QDate.currentDate())
        date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(date_label)
        date_layout.addWidget(date_input)

        amount_layout = QHBoxLayout()
        amount_label = QLabel("金额:")
        amount_input = QLineEdit()
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(amount_input)

        currency_layout = QHBoxLayout()
        currency_label = QLabel("币种:")
        currency_combobox = QComboBox()
        currency_combobox.addItems(["人民币 (CNY)", "美元 (USD)", "欧元 (EUR)", "日元 (JPY)", "其他"])
        currency_layout.addWidget(currency_label)
        currency_layout.addWidget(currency_combobox)

        type_layout = QHBoxLayout()
        type_label = QLabel("收支类型:")
        type_combobox = QComboBox()
        type_combobox.addItems(["收入", "支出"])
        type_layout.addWidget(type_label)
        type_layout.addWidget(type_combobox)

        category_layout = QHBoxLayout()
        category_label = QLabel("详细分类:")
        category_combobox = QComboBox()
        income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
        expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
        category_combobox.addItems(income_categories + expense_categories)
        category_layout.addWidget(category_label)
        category_layout.addWidget(category_combobox)

        note_layout = QHBoxLayout()
        note_label = QLabel("备注信息:")
        note_input = QLineEdit()
        note_layout.addWidget(note_label)
        note_layout.addWidget(note_input)

        button_layout = QHBoxLayout()
        modify_button = QPushButton("修改记录")
        modify_button.clicked.connect(lambda: self.update_record(
            record_id,
            date_input.date().toString("yyyy-MM-dd"),
            amount_input.text(),
            currency_combobox.currentText(),
            type_combobox.currentText(),
            category_combobox.currentText(),
            note_input.text(),
            modify_dialog
        ))
        button_layout.addWidget(modify_button)

        modify_layout.addLayout(date_layout)
        modify_layout.addLayout(amount_layout)
        modify_layout.addLayout(currency_layout)
        modify_layout.addLayout(type_layout)
        modify_layout.addLayout(category_layout)
        modify_layout.addLayout(note_layout)
        modify_layout.addLayout(button_layout)

        modify_dialog.setLayout(modify_layout)
        modify_dialog.exec_()

    def update_record(self, record_id, date, amount_str, currency, type_, category, note, dialog):
        try:
            amount = float(amount_str)
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return

        self.cursor.execute("UPDATE records SET date=?, amount=?, currency=?, type=?, category=?, note=? WHERE id=?",
                            (date, amount, currency, type_, category, note, record_id))
        self.conn.commit()
        self.load_records()
        dialog.close()

    def show_export_prompt(self):
        QMessageBox.information(self, "导出功能", "导出功能暂未实现！")

    def show_import_prompt(self):
        QMessageBox.information(self, "导入功能", "导入功能暂未实现！")

    def show_about_info(self):
        QMessageBox.about(self, "关于", "记账本程序\n版本: 0.01\n开发者: 机器人团队")

    def update_time(self):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.time_label.setText(f"UTC+8 {current_time}")

    def update_bottom_info(self):
        system = platform.system()
        release = platform.release()
        version = platform.version()
        architecture = platform.architecture()[0]

        self.bottom_info.setText(
            f"运行于: {system} {release} {architecture}\n"
            f"当前用户: {self.current_user}\n"
            f"软件版本: Version.0.01"
        )

    def show_settings_dialog(self):
        """显示设置对话框"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setGeometry(100, 100, 600, 400)

        # 创建主布局
        main_layout = QHBoxLayout(self)

        # 创建左侧菜单栏
        self.menu_list = QListWidget()
        self.menu_list.setFixedWidth(150)
        self.menu_list.setStyleSheet("""
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #ddd;
                background-color: white;
            }
            QListWidget::item:selected {
                background-color: white;
                border-left: 3px solid #4CAF50;
                color: #4CAF50;
            }
        """)
        menu_items = ["主题", "账号设置", "消息通知", "通用设置", "文件管理", "快捷键", "关于"]
        for item in menu_items:
            list_item = QListWidgetItem(item)
            self.menu_list.addItem(list_item)
        self.menu_list.setCurrentRow(0)  # 默认选中第一项

        # 创建右侧内容区域
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("""
            background-color: white;
            border-left: 1px solid #eee;
        """)

        # 添加每个菜单项对应的内容页面
        self.add_menu_page("主题", self.create_theme_settings_page())
        self.add_menu_page("账号设置", self.create_account_settings_page())
        self.add_menu_page("消息通知", self.create_message_settings_page())
        self.add_menu_page("通用设置", self.create_general_settings_page())
        self.add_menu_page("文件管理", self.create_file_management_page())
        self.add_menu_page("快捷键", self.create_shortcuts_page())
        self.add_menu_page("关于", self.create_about_page())

        # 连接菜单项点击事件
        self.menu_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        # 添加到主布局
        main_layout.addWidget(self.menu_list)
        main_layout.addWidget(self.stacked_widget)

    def add_menu_page(self, title, widget):
        """添加菜单项对应的内容页面"""
        self.stacked_widget.addWidget(widget)

    def create_account_settings_page(self):
        """创建账号设置页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("账号设置内容"))
        layout.addStretch()
        return page

    def create_message_settings_page(self):
        """创建消息通知页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("消息通知内容"))
        layout.addStretch()
        return page

    def create_general_settings_page(self):
        """创建通用设置页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("通用设置内容"))
        layout.addStretch()
        return page

    def create_file_management_page(self):
        """创建文件管理页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("文件管理内容"))
        layout.addStretch()
        return page

    def create_shortcuts_page(self):
        """创建快捷键页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("快捷键内容"))
        layout.addStretch()
        return page

    def create_about_page(self):
        """创建关于页面，包含版权声明"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # 添加版本信息和图标
        version_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap('app_icon.png')  # 替换为您的图标路径
        icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio))
        version_layout.addWidget(icon_label)
        version_label = QLabel("使用条款、版权声明与开源协议")
        version_label.setStyleSheet("font-size: 18px; color: #333;")
        version_layout.addWidget(version_label)
        version_layout.addStretch()
        layout.addLayout(version_layout)

        # 添加版权声明
        copyright_text = """
        记账本程序
        Copyright 2025 长治市屯留区机器人社团 饶晨曦, 姜震岳 原新然 路志博 刘以恩
        All Rights Reserved.

        This software is the confidential and proprietary information of
        长治市屯留区机器人社团 ("Confidential Information").
        You shall not disclose such Confidential Information and shall use
        it only in accordance with the terms of the license agreement you entered into with 长治市屯留区机器人社团.
        记账本程序
        Copyright 2025 长治市屯留区机器人社团 饶晨曦, 姜震岳 原新然 路志博 刘以恩
        All Rights Reserved.

        This software is the confidential and proprietary information of
        长治市屯留区机器人社团 ("Confidential Information").
        You shall not disclose such Confidential Information and shall use
        it only in accordance with the terms of the license agreement you entered into with 长治市屯留区机器人社团
        .

        用户许可协议部分：
        记账本程序用户许可协议
        一、版权声明
        记账本程序（以下简称 "本软件"）由长治市屯留区机器人社团（以下简称 "开发者"）开发并拥有。本软件的一切版权、商标权、专利权、商业秘密等知识产权均归开发者所有。本协议旨在规定用户使用本软件时的权利与义务。
        二、许可范围
        非商业使用许可：开发者授予用户个人非商业性质的、可撤销的、非排他的使用许可。用户可在个人计算机或其他个人设备上安装、使用本软件。
        禁止分发与传播：未经开发者书面许可，用户不得以任何形式或任何途径分发、传播、出租、出售本软件，包括但不限于通过互联网、局域网、光盘等介质。
        禁止修改与逆向工程：用户不得对本软件进行反向工程、反编译、修改源代码或创建衍生作品。用户不得删除或修改本软件中的任何版权标识或商标。
        三、用户权利
        使用权利：在遵守本协议的前提下，用户有权使用本软件提供的各项功能，包括但不限于记录、查询、修改、删除个人记账信息。
        隐私保护权利：用户有权要求开发者保护其个人信息及记账数据，不得泄露给第三方，除非法律另有规定或用户书面同意。
        软件更新权利：用户有权获得开发者提供的本软件的更新版本，以提升使用体验和功能。
        四、用户义务
        合法使用义务：用户应遵守相关法律法规，不得利用本软件进行任何违法活动，包括但不限于洗钱、诈骗、侵犯他人权益等。
        不侵权义务：用户不得侵犯开发者的知识产权或其他第三方的合法权益。
        维护软件完整性义务：用户不得破坏本软件的技术保护措施或完整性，不得干扰本软件的正常运行。
        数据备份义务：用户应定期备份个人记账数据，以防数据丢失或损坏。
        五、隐私政策
        信息收集：本软件在运行过程中可能收集用户的设备信息、操作行为等数据，但不会收集用户的个人身份信息，除非用户自愿提供。
        信息使用：收集到的数据将仅用于软件功能的实现和优化，不会用于其他目的或泄露给第三方，除非法律要求或用户书面同意。
        数据安全：开发者将采取合理的技术和管理措施保护用户数据的安全，防止数据泄露、损坏或丢失。
        六、免责声明
        软件按现状提供：本软件按现状提供，开发者不保证其无瑕疵、无病毒或完全符合用户需求。用户自行承担使用风险。
        不保证持续运行：开发者不保证本软件始终可用或无中断。因网络故障、服务器维护等原因导致的暂时无法使用，开发者不承担责任。
        不承担间接损失：对于因使用本软件而产生的间接、附带或后果性的损失（包括但不限于数据丢失、利润减少等），开发者不承担责任。
        七、协议的终止
        用户违约导致的终止：若用户违反本协议的任何条款，开发者有权单方面终止本协议，并可能要求用户停止使用本软件、删除软件等。
        开发者权利：协议终止后，用户应立即停止使用本软件，并删除或销毁软件的全部副本。开发者有权收回用户因本协议获得的所有权利。
        八、争议解决
        协商解决：因本协议引起的任何争议，双方应首先通过友好协商解决；协商不成的，任何一方均有权向有管辖权的人民法院提起诉讼。
        适用法律：本协议的订立、执行和解释均适用中华人民共和国法律。
        九、协议的修改
        开发者有权根据需要修改本协议。修改后的协议将通过软件更新或官方网站公布。用户继续使用本软件视为接受修改后的协议。
        十、联系方式
        如您对本协议有任何疑问或需要进一步的信息，请联系开发者：
        长治市屯留区机器人社团
        联系人：饶晨曦、姜震岳、原新然、路志博、刘以恩
        邮箱：暂无
        电话：暂无
        地址：长治市屯留区
        邮编：046100
        日期：2025年3月26日
        备注：该软件遵循Apache License (Version 2.0, January 2004)进行开源。



        开源许可证部分：
        阿帕奇许可证 2.0
        Apache License
        Version 2.0, January 2004
        http://www.apache.org/licenses/
        TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
        Definitions.
        "License" shall mean the terms and conditions for use, reproduction, and distribution as defined by Sections 1 through 9 of this document.
        "Licensor" shall mean the copyright owner or entity authorized by the copyright owner that is granting the License.
        "Legal Entity" shall mean the union of the acting entity and all other entities that control, are controlled by, or are under common control with that entity. For the purposes of this definition, "control" means (i) the power, direct or indirect, to cause the direction or management of such entity, whether by contract or otherwise, or (ii) ownership of fifty percent (50%) or more of the outstanding shares, or (iii) beneficial ownership of such entity.
        "You" (or "Your") shall mean an individual or Legal Entity exercising permissions granted by this License.
        "Source" form shall mean the preferred form for making modifications, including but not limited to software source code, documentation source, and configuration files.
        "Object" form shall mean any form resulting from mechanical transformation or translation of a Source form, including but not limited to compiled object code, generated documentation, and conversions to other media types.
        "Work" shall mean the work of authorship, whether in Source or Object form, made available under the License, as indicated by a copyright notice that is included in or attached to the work (an example is provided in the Appendix).
        "Derivative Works" shall mean any work, whether in Source or Object form, that is based on (or derived from) the Work and for which the editorial revisions, annotations, elaborations, or other modifications represent, as a whole, an original work of authorship. For the purposes of this License, Derivative Works shall not include works that remain separable from, or merely link (or bind by name) to the interfaces of, the Work and Derivative Works thereof.
        "Contribution" shall mean any work of authorship, including the original version of the Work and any modifications or additions to that Work or Derivative Works thereof, that is intentionally submitted to Licensor for inclusion in the Work by the copyright owner or by an individual or Legal Entity authorized to submit on behalf of the copyright owner. For the purposes of this definition, "submitted" means any form of electronic, verbal, or written communication sent to the Licensor or its representatives, including but not limited to communication on electronic mailing lists, source code control systems, and issue tracking systems that are managed by, or on behalf of, the Licensor for the purpose of discussing and improving the Work, but excluding communication that is conspicuously marked or otherwise designated in writing by the copyright owner as "Not a Contribution."
        "Contributor" shall mean Licensor and any individual or Legal Entity on behalf of whom a Contribution has been received by Licensor and subsequently incorporated within the Work.
        Grant of Copyright License. Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works in Source or Object form.
        Grant of Patent License. Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license under licensed patents to make, use, sell, offer for sale, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by such Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted. If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes separate or combined infringement of a patent, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.
        Redistribution. You may reproduce and distribute copies of the Work or Derivative Works thereof in any medium, with or without modifications, and in Source or Object form, provided that You meet the following conditions:
        a. You must give any other recipients of the Work or Derivative Works a copy of this License; and
        b. You must cause any modified files to carry prominent notices stating that You changed the files; and
        c. You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, and attribution notices from the Source form of the Work, excluding those notices that do not pertain to any part of the Derivative Works; and
        d. If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute must include a readable copy of the attribution notices contained within such NOTICE file, excluding those notices that do not pertain to any part of the Derivative Works, in at least one of the following places: within a NOTICE text file distributed as part of the Derivative Works; within the Source form or documentation, if provided along with the Derivative Works; or, within a display generated by the Derivative Works, if and wherever such third-party notices normally appear. The contents of the NOTICE file are for informational purposes only and do not modify the License. You may add Your own attribution notices within Derivative Works that You distribute, alongside or as an addendum to the NOTICE text from the Work, provided that such additional notices cannot be construed as modifying the License.
        You may add Your own copyright statement to Your modifications and may provide additional or different license terms and conditions for use, reproduction, or distribution of Your modifications, or for any such Derivative Works as a whole, provided Your use, reproduction, and distribution of the Work otherwise complies with the conditions stated in this License.
        Submission of Contributions. Unless You explicitly state otherwise, any Contribution intentionally submitted for inclusion in the Work by You to the Licensor shall be under the terms and conditions of this License, without any additional terms or conditions. Notwithstanding the above, nothing herein shall supersede or modify the terms of any separate license agreement you may have executed with Licensor regarding such Contributions.
        Trademarks. This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor, except as required for reasonable and customary use in describing the origin of the Work and reproducing the content of the NOTICE file.
        Disclaimer of Warranty. Unless required by applicable law or agreed to in writing, Licensor provides the Work (and each Contributor provides its Contributions) on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied, including, without limitation, any warranties or conditions of TITLE, NONINFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A PARTICULAR PURPOSE. You are solely responsible for determining the appropriateness of using or redistributing the Work and assume any risks associated with Your exercise of permissions under this License.
        Limitation of Liability. In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, unless required by applicable law (such as deliberate and grossly negligent acts) or agreed to in writing, shall any Contributor be liable to You for damages, including any direct, indirect, special, incidental, or consequential damages of any character arising as a result of this License or out of the use or inability to use the Work (including but not limited to damages for loss of goodwill, work stoppage, computer failure or malfunction, or any and all other commercial damages or losses), even if such Contributor has been advised of the possibility of such damages.
        Accepting Warranty or Additional Liability. While redistributing the Work or Derivative Works thereof, You may choose to offer, and charge a fee for, acceptance of support, warranty, indemnity, or other liabilities to or for Users of the Work or Derivative Works. However, in accepting such obligations, You may act only on Your own behalf and on Your sole responsibility, not on behalf of any other Contributor, and only if You agree to indemnify, defend, and hold each Contributor harmless for any liability incurred by, or claims asserted against, such Contributor by reason of your accepting any such warranty or additional liability.
        END OF TERMS AND CONDITIONS
        APPENDIX: How to apply the Apache License to your work.
        To apply the Apache License to your work, attach the following boilerplate notice, with the fields enclosed by brackets "[]" replaced with your own identifying information. (Don't include the brackets!) The text should be enclosed in the appropriate comment syntax for the file format. We also recommend that a file or class name and description of purpose be included on the same "printed page" as the copyright notice for earlier versions of the file, if any, or this license, hence the license itself.
        Copyright [2025] [长治市屯留区机器人社团]
        Licensed under the Apache License, Version 2.0 (the "License");
        you may not use this file except in compliance with the License.
        You may obtain a copy of the License at
           http://www.apache.org/licenses/LICENSE-2.0
        Unless required by applicable law or agreed to in writing, software
        distributed under the License is distributed on an "AS IS" BASIS,
        WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
        See the License for the specific language governing permissions and
        limitations under the License.



        我们特为中国用户提供适合本记账本程序项目的中文修改版：

        //修改说明：
        版权信息：将版权年份和版权所有者信息修改为适合记账本程序项目的内容。
        许可范围：明确许可的使用范围，确保符合记账本程序项目的开源策略。
        贡献提交：调整贡献提交的条款，使其更适合社区贡献的管理。
        责任限制：根据项目需求，调整责任限制的条款，确保项目方的责任合理界定。
        商标使用：明确商标使用的限制，避免不必要的商标纠纷。
        //
        修改后的中文版阿帕奇 2.0 许可证:
  
        
        记账本程序 - Apache 2.0 许可证
        版权声明
        版权所有 (C) 2025 长治市屯留区机器人社团 饶晨曦、姜震岳、原新然、路志博、刘以恩
        特此授予 Apache 2.0 许可证（"许可证"）；您可以在以下条件下使用、复制和分发此软件：
        您必须在任何副本中包含原始版权声明、许可声明和免责声明。
        如果您对此软件进行了修改，必须在修改的文件中添加显著的声明，说明您进行了修改。
        如果软件包含 "NOTICE" 文件，您必须在分发的任何衍生作品中包含原始 NOTICE 文件的内容。
        除非适用法律要求或书面同意，许可人按 "原样" 提供软件，不附带任何明示或暗示的保证，包括但不限于对软件所有权、非侵权性、适销性和特定用途适用性的保证。您自行承担使用和分发软件的风险。
        在任何情况下，无论基于何种法律理论（包括但不限于侵权、合同或其他），除非适用法律要求或书面同意，否则任何贡献者均不对因使用或无法使用软件而引起的任何直接、间接、特殊、偶然或后果性损害（包括但不限于商誉损失、停工、计算机故障或任何其他商业损害或损失）承担责任，即使贡献者已被告知可能发生此类损害。
        适用法律
        本许可证受中华人民共和国法律管辖并按其解释。
        许可证接受
        通过使用、复制或分发软件，您即表示接受并同意遵守本许可证的所有条款和条件。
        长治市屯留区机器人社团：
        饶晨曦、姜震岳、原新然、路志博、刘以恩
         2025年3月26日
        """
        copyright_label = QTextEdit()
        copyright_label.setReadOnly(True)
        copyright_label.setText(copyright_text)
        copyright_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        layout.addWidget(copyright_label)

        layout.addStretch()
        return page

    def create_theme_settings_page(self):
        """创建主题设置页面"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # 主题选择标签
        theme_label = QLabel("选择主题：")
        layout.addWidget(theme_label)

        # 预设主题选择框
        self.theme_combobox = QComboBox()
        self.theme_combobox.addItems(["默认主题", "清新蓝绿风格", "优雅紫金风格", "现代灰绿风格", "专业深色风格", "明亮活泼风格", "自定义主题"])
        self.theme_combobox.currentIndexChanged.connect(self.apply_theme)
        layout.addWidget(self.theme_combobox)

        # 自定义主题颜色设置
        custom_theme_group = QGroupBox("自定义主题颜色")
        custom_theme_layout = QVBoxLayout()

        # 主背景色
        background_color_layout = QHBoxLayout()
        background_color_label = QLabel("主背景色：")
        self.background_color_btn = QPushButton()
        self.background_color_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        self.background_color_btn.setFixedSize(30, 30)
        self.background_color_btn.clicked.connect(lambda: self.show_color_dialog(self.background_color_btn))
        background_color_layout.addWidget(background_color_label)
        background_color_layout.addWidget(self.background_color_btn)
        background_color_layout.addStretch()
        custom_theme_layout.addLayout(background_color_layout)

        # 按钮颜色
        button_color_layout = QHBoxLayout()
        button_color_label = QLabel("按钮颜色：")
        self.button_color_btn = QPushButton()
        self.button_color_btn.setStyleSheet("background-color: #4a90e2; border: 1px solid #ccc;")
        self.button_color_btn.setFixedSize(30, 30)
        self.button_color_btn.clicked.connect(lambda: self.show_color_dialog(self.button_color_btn))
        button_color_layout.addWidget(button_color_label)
        button_color_layout.addWidget(self.button_color_btn)
        button_color_layout.addStretch()
        custom_theme_layout.addLayout(button_color_layout)

        # 标题颜色
        title_color_layout = QHBoxLayout()
        title_color_label = QLabel("标题颜色：")
        self.title_color_btn = QPushButton()
        self.title_color_btn.setStyleSheet("background-color: #2c3e50; border: 1px solid #ccc;")
        self.title_color_btn.setFixedSize(30, 30)
        self.title_color_btn.clicked.connect(lambda: self.show_color_dialog(self.title_color_btn))
        title_color_layout.addWidget(title_color_label)
        title_color_layout.addWidget(self.title_color_btn)
        title_color_layout.addStretch()
        custom_theme_layout.addLayout(title_color_layout)

        # 选中项颜色
        selected_color_layout = QHBoxLayout()
        selected_color_label = QLabel("选中项颜色：")
        self.selected_color_btn = QPushButton()
        self.selected_color_btn.setStyleSheet("background-color: #e3f2fd; border: 1px solid #ccc;")
        self.selected_color_btn.setFixedSize(30, 30)
        self.selected_color_btn.clicked.connect(lambda: self.show_color_dialog(self.selected_color_btn))
        selected_color_layout.addWidget(selected_color_label)
        selected_color_layout.addWidget(self.selected_color_btn)
        selected_color_layout.addStretch()
        custom_theme_layout.addLayout(selected_color_layout)

        custom_theme_group.setLayout(custom_theme_layout)
        layout.addWidget(custom_theme_group)

        # 应用按钮
        apply_button = QPushButton("应用自定义主题")
        apply_button.clicked.connect(self.apply_custom_theme)
        layout.addWidget(apply_button, alignment=Qt.AlignCenter)

        layout.addStretch()
        return page

    def show_color_dialog(self, button):
        """显示颜色选择对话框"""
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")

    def apply_theme(self, index):
        """应用选择的主题"""
        themes = {
            0: self.apply_default_theme,
            1: self.apply_fresh_blue_green_theme,
            2: self.apply_elegant_purple_gold_theme,
            3: self.apply_modern_gray_green_theme,
            4: self.apply_professional_dark_theme,
            5: self.apply_bright_lively_theme,
            6: self.apply_custom_theme
        }
        if index in themes:
            themes[index]()

    def apply_default_theme(self):
        """应用默认主题"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                color: #333333;
            }
            QPushButton {
                background-color: #4a90e2;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QLabel {
                color: #2c3e50;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)

    def apply_fresh_blue_green_theme(self):
        """应用清新蓝绿风格"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #f5f9fc;
                color: #333333;
            }
            QPushButton {
                background-color: #4a90e2;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QLabel {
                color: #2c3e50;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)

    def apply_elegant_purple_gold_theme(self):
        """应用优雅紫金风格"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #f9f6f0;
                color: #333333;
            }
            QPushButton {
                background-color: #9c27b0;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7b1fa2;
            }
            QLabel {
                color: #4a148c;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #e1bee7;
                color: #7b1fa2;
            }
        """)

    def apply_modern_gray_green_theme(self):
        """应用现代灰绿风格"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                color: #333333;
            }
            QPushButton {
                background-color: #4caf50;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
            QLabel {
                color: #2e7d32;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #e8f5e9;
                color: #2e7d32;
            }
        """)

    def apply_professional_dark_theme(self):
        """应用专业深色风格"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #f0f0f0;
            }
            QPushButton {
                background-color: #2196f3;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QLabel {
                color: #bbdefb;
            }
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #333333;
            }
            QListWidget::item:selected {
                background-color: #333333;
                color: #2196f3;
            }
        """)

    def apply_bright_lively_theme(self):
        """应用明亮活泼风格"""
        self.parent().setStyleSheet("""
            QWidget {
                background-color: #fff3e0;
                color: #333333;
            }
            QPushButton {
                background-color: #ff5722;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e64a19;
            }
            QLabel {
                color: #bf360c;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #ffe0b2;
                color: #bf360c;
            }
        """)

    def apply_custom_theme(self):
        """应用自定义主题"""
        background_color = self.background_color_btn.styleSheet().split(';')[0].split(':')[1].strip()
        button_color = self.button_color_btn.styleSheet().split(';')[0].split(':')[1].strip()
        title_color = self.title_color_btn.styleSheet().split(';')[0].split(':')[1].strip()
        selected_color = self.selected_color_btn.styleSheet().split(';')[0].split(':')[1].strip()

        self.parent().setStyleSheet(f"""
            QWidget {{
                background-color: {background_color};
                color: #333333;
            }}
            QPushButton {{
                background-color: {button_color};
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {self.darken_color(button_color)};
            }}
            QLabel {{
                color: {title_color};
            }}
            QTableWidget {{
                background-color: white;
                border: 1px solid #e0e0e0;
            }}
            QListWidget::item:selected {{
                background-color: {selected_color};
                color: {self.contrast_color(selected_color)};
            }}
        """)

    def darken_color(self, color):
        """使颜色变暗"""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r = int(r * 0.8)
        g = int(g * 0.8)
        b = int(b * 0.8)
        return f"#{r:02x}{g:02x}{b:02x}"

    def contrast_color(self, color):
        """获取对比色"""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#000000" if luminance > 0.5 else "#ffffff"


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AccountingApp()
    ex.show()
    sys.exit(app.exec_())

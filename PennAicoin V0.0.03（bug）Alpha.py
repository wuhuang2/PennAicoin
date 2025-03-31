import sys
import sqlite3
import wave
import json
import re
import vosk
import pyaudio
import jieba
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView, QSizePolicy
)
from PyQt5.QtCore import QDate, Qt, QThread, pyqtSignal


class VoiceRecognition(QThread):
    recognized_text = pyqtSignal(str)

    def __init__(self, model_path, timeout=60):
        super().__init__()
        self.model_path = model_path
        self.is_recording = False
        self.frames = []
        self.start_time = 0  # 录音开始时间
        self.timeout = timeout  # 录音超时时间（秒）

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
                frames_per_buffer=8000
            )
            print("模型加载成功，开始录音...")
            self.is_recording = True
            self.frames = []
            self.start_time = time.time()  # 记录录音开始时间
            while self.is_recording:
                data = self.stream.read(4000)
                self.frames.append(data)
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    print("语音识别结果:", result["text"])
                    self.stop_recording()
                    self.recognized_text.emit(result["text"])
                    break
                # 检查是否超时
                elapsed_time = time.time() - self.start_time
                if elapsed_time >= self.timeout:
                    print("录音超时，自动停止...")
                    self.stop_recording()
                    self.recognized_text.emit("")  # 发送空字符串表示超时
                    break
            print("语音识别结束，处理识别结果...")
            result = json.loads(self.recognizer.FinalResult())
            self.recognized_text.emit(result.get("text", ""))
            self.stream.stop_stream()
            self.stream.close()
            self.p.terminate()
            print("音频资源已释放")

            # 保存音频到文件
            self.save_audio("voice.wav")
        except Exception as e:
            print("语音识别线程出错:", e)

    def stop_recording(self):
        print("停止录音...")
        self.is_recording = False

    def save_audio(self, filename):
        """将录音保存为 WAV 文件"""
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

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle('记账本程序')
        self.setGeometry(100, 100, 1200, 800)

        # 设置样式表
        self.setStyleSheet(self.style_sheet())

        # 顶部菜单栏
        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        self.menu_bar.addMenu('文件')
        self.menu_bar.addMenu('编辑')
        self.menu_bar.addMenu('查看')
        self.menu_bar.addMenu('帮助')

        # 左侧工具栏
        self.tool_bar = QToolBar(self)
        self.addToolBar(self.tool_bar)

        # 侧边栏
        self.side_bar = QVBoxLayout()
        self.side_bar.setAlignment(Qt.AlignTop)  # 使按钮靠上对齐
        self.side_bar.setSpacing(10)  # 按钮之间的间隔

        # 搜索记录按钮
        self.search_record_button = QPushButton('搜索记录')
        self.search_record_button.setFixedHeight(40)
        self.search_record_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_record_button.clicked.connect(self.show_search_dialog)
        self.side_bar.addWidget(self.search_record_button)

        # 添加账本按钮
        self.add_button = QPushButton('添加账本')
        self.add_button.setFixedHeight(40)
        self.add_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_button.clicked.connect(self.show_add_dialog)
        self.side_bar.addWidget(self.add_button)

        # 回收站按钮
        self.delete_button = QPushButton('回收站')
        self.delete_button.setFixedHeight(40)
        self.delete_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_record)
        self.side_bar.addWidget(self.delete_button)

        # 语音输入按钮
        self.voice_button = QPushButton('开始录音')
        self.voice_button.setFixedHeight(40)
        self.voice_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_button.clicked.connect(self.toggle_recording)
        self.side_bar.addWidget(self.voice_button)

        # 修改按钮
        self.modify_button = QPushButton('修改')
        self.modify_button.setFixedHeight(40)
        self.modify_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.modify_button.clicked.connect(self.modify_record)
        self.side_bar.addWidget(self.modify_button)

        # 中央窗口
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 主布局
        self.main_layout = QHBoxLayout(self.central_widget)

        # 添加侧边栏和表格
        self.main_layout.addLayout(self.side_bar, 1)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["日期", "金额", "币种", "收支类型", "详细分类", "备注信息"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.main_layout.addWidget(self.table, 4)

    def init_db(self):
        """初始化数据库"""
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
        """从数据库加载记录并显示在表格中"""
        self.cursor.execute("SELECT * FROM records")
        records = self.cursor.fetchall()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(record[1]))
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.table.setItem(row, 5, QTableWidgetItem(record[6]))

    def toggle_recording(self):
        """切换录音状态"""
        print("切换录音状态...")
        try:
            if self.voice_thread and self.voice_thread.isRunning():
                self.stop_recording()
            else:
                self.start_recording()
        except Exception as e:
            print("切换录音状态时出错:", e)

    def start_recording(self):
        """开始录音"""
        print("开始录音...")
        try:
            self.voice_button.setText('结束录音')
            model_path = "path/to/vosk_model"  # 替换为 vosk 模型路径
            timeout = 60  # 录音超时时间（秒）
            self.voice_thread = VoiceRecognition(model_path, timeout)
            self.voice_thread.recognized_text.connect(self.process_voice_input)
            self.voice_thread.start()
        except Exception as e:
            print("开始录音时出错:", e)

    def stop_recording(self):
        """停止录音"""
        print("停止录音...")
        try:
            self.voice_button.setText('开始录音')
            if self.voice_thread and self.voice_thread.isRunning():
                self.voice_thread.recognizer.is_recording = False
                self.voice_thread.quit()  # 确保线程退出
                self.voice_thread.wait()  # 等待线程完成
        except Exception as e:
            print("停止录音时出错:", e)

    def process_voice_input(self, recognized_text):
        """处理语音输入"""
        print("处理语音输入...")
        if recognized_text:
            print("识别到的语音:", recognized_text)
            # 使用 jieba 分词提取信息
            words = jieba.lcut(recognized_text)
            date = self.extract_date(words)
            amount = self.extract_amount(words)
            currency = self.extract_currency(words)
            type_ = self.extract_type(words)
            category = self.extract_category(words)
            note = self.extract_note(words)

            # 添加记录
            self.add_record(date, amount, currency, type_, category, note)
        else:
            print("语音识别超时，未获取到有效内容")

    def extract_date(self, words):
        """提取日期"""
        date_pattern = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日')
        for word in words:
            if date_pattern.match(word):
                return word.replace('年', '-').replace('月', '-').replace('日', '')
        return QDate.currentDate().toString("yyyy-MM-dd")

    def extract_amount(self, words):
        """提取金额"""
        amount_pattern = re.compile(r'\d+\.?\d*')
        for word in words:
            match = amount_pattern.findall(word)
            if match:
                return float(match[0])
        return 0.0

    def extract_currency(self, words):
        """提取币种"""
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
        """提取收支类型"""
        if '收入' in words:
            return '收入'
        elif '支出' in words:
            return '支出'
        else:
            return '支出'

    def extract_category(self, words):
        """提取分类"""
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
        """提取备注"""
        return ' '.join(words)

    def add_record(self, date, amount, currency, type_, category, note):
        """添加记录到数据库"""
        print("添加记录到数据库...")
        self.cursor.execute("INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
                            (date, amount, currency, type_, category, note))
        self.conn.commit()
        self.load_records()

    def show_search_dialog(self):
        """显示搜索对话框"""
        search_dialog = QDialog(self)
        search_dialog.setWindowTitle('搜索记录')
        search_layout = QVBoxLayout()
        search_input = QLineEdit()
        search_input.setPlaceholderText("输入搜索内容")
        search_layout.addWidget(search_input)
        search_button = QPushButton('搜索')
        search_button.clicked.connect(lambda: self.search_records(search_input.text()))
        search_layout.addWidget(search_button)
        search_dialog.setLayout(search_layout)
        search_dialog.exec_()

    def search_records(self, query):
        """根据搜索框中的关键词搜索记录"""
        self.cursor.execute("SELECT * FROM records WHERE note LIKE ?", (f'%{query}%',))
        records = self.cursor.fetchall()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(record[1]))
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.table.setItem(row, 5, QTableWidgetItem(record[6]))

    def show_add_dialog(self):
        """显示添加账本对话框"""
        add_dialog = QDialog(self)
        add_dialog.setWindowTitle('添加账本')
        add_layout = QVBoxLayout()

        # 日期输入
        date_layout = QHBoxLayout()
        date_label = QLabel("日期:")
        date_input = QDateEdit()
        date_input.setDate(QDate.currentDate())
        date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(date_label)
        date_layout.addWidget(date_input)

        # 金额输入
        amount_layout = QHBoxLayout()
        amount_label = QLabel("金额:")
        amount_input = QLineEdit()
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(amount_input)

        # 币种输入
        currency_layout = QHBoxLayout()
        currency_label = QLabel("币种:")
        currency_combobox = QComboBox()
        currency_combobox.addItems(["人民币 (CNY)", "美元 (USD)", "欧元 (EUR)", "日元 (JPY)", "其他"])
        currency_layout.addWidget(currency_label)
        currency_layout.addWidget(currency_combobox)

        # 收支类型输入
        type_layout = QHBoxLayout()
        type_label = QLabel("收支类型:")
        type_combobox = QComboBox()
        type_combobox.addItems(["收入", "支出"])
        type_layout.addWidget(type_label)
        type_layout.addWidget(type_combobox)

        # 详细分类输入
        category_layout = QHBoxLayout()
        category_label = QLabel("详细分类:")
        category_combobox = QComboBox()
        income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
        expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
        category_combobox.addItems(income_categories + expense_categories)
        category_layout.addWidget(category_label)
        category_layout.addWidget(category_combobox)

        # 备注输入
        note_layout = QHBoxLayout()
        note_label = QLabel("备注信息:")
        note_input = QLineEdit()
        note_layout.addWidget(note_label)
        note_layout.addWidget(note_input)

        # 按钮布局
        button_layout = QHBoxLayout()
        add_button = QPushButton("添加记录")
        add_button.clicked.connect(lambda: self.add_record(date_input, amount_input, currency_combobox, type_combobox, category_combobox, note_input, add_dialog))
        button_layout.addWidget(add_button)

        # 添加布局
        add_layout.addLayout(date_layout)
        add_layout.addLayout(amount_layout)
        add_layout.addLayout(currency_layout)
        add_layout.addLayout(type_layout)
        add_layout.addLayout(category_layout)
        add_layout.addLayout(note_layout)
        add_layout.addLayout(button_layout)

        add_dialog.setLayout(add_layout)
        add_dialog.exec_()

    def add_record(self, date_input, amount_input, currency_combobox, type_combobox, category_combobox, note_input, dialog):
        """添加记录到数据库"""
        date = date_input.date().toString("yyyy-MM-dd")
        try:
            amount = float(amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return

        currency = currency_combobox.currentText()
        type_ = type_combobox.currentText()
        category = category_combobox.currentText()
        note = note_input.text()

        self.cursor.execute("INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
                            (date, amount, currency, type_, category, note))
        self.conn.commit()
        self.load_records()
        dialog.close()

    def delete_record(self):
        """删除选中的记录"""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return
        record_id = selected_row + 1

        reply = QMessageBox.question(self, "确认删除", "确定要删除这条记录吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.cursor.execute("DELETE FROM records WHERE id=?", (record_id,))
            self.conn.commit()
            self.load_records()

    def modify_record(self):
        """修改选中的记录"""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return
        record_id = selected_row + 1

        modify_dialog = QDialog(self)
        modify_dialog.setWindowTitle('修改记录')
        modify_layout = QVBoxLayout()

        # 日期输入
        date_layout = QHBoxLayout()
        date_label = QLabel("日期:")
        date_input = QDateEdit()
        date_input.setDate(QDate.currentDate())
        date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(date_label)
        date_layout.addWidget(date_input)

        # 金额输入
        amount_layout = QHBoxLayout()
        amount_label = QLabel("金额:")
        amount_input = QLineEdit()
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(amount_input)

        # 币种输入
        currency_layout = QHBoxLayout()
        currency_label = QLabel("币种:")
        currency_combobox = QComboBox()
        currency_combobox.addItems(["人民币 (CNY)", "美元 (USD)", "欧元 (EUR)", "日元 (JPY)", "其他"])
        currency_layout.addWidget(currency_label)
        currency_layout.addWidget(currency_combobox)

        # 收支类型输入
        type_layout = QHBoxLayout()
        type_label = QLabel("收支类型:")
        type_combobox = QComboBox()
        type_combobox.addItems(["收入", "支出"])
        type_layout.addWidget(type_label)
        type_layout.addWidget(type_combobox)

        # 详细分类输入
        category_layout = QHBoxLayout()
        category_label = QLabel("详细分类:")
        category_combobox = QComboBox()
        income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
        expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
        category_combobox.addItems(income_categories + expense_categories)
        category_layout.addWidget(category_label)
        category_layout.addWidget(category_combobox)

        # 备注输入
        note_layout = QHBoxLayout()
        note_label = QLabel("备注信息:")
        note_input = QLineEdit()
        note_layout.addWidget(note_label)
        note_layout.addWidget(note_input)

        # 按钮布局
        button_layout = QHBoxLayout()
        modify_button = QPushButton("修改记录")
        modify_button.clicked.connect(lambda: self.update_record(date_input, amount_input, currency_combobox, type_combobox, category_combobox, note_input, record_id, modify_dialog))
        button_layout.addWidget(modify_button)

        # 添加布局
        modify_layout.addLayout(date_layout)
        modify_layout.addLayout(amount_layout)
        modify_layout.addLayout(currency_layout)
        modify_layout.addLayout(type_layout)
        modify_layout.addLayout(category_layout)
        modify_layout.addLayout(note_layout)
        modify_layout.addLayout(button_layout)

        modify_dialog.setLayout(modify_layout)
        modify_dialog.exec_()

    def update_record(self, date_input, amount_input, currency_combobox, type_combobox, category_combobox, note_input, record_id, dialog):
        """更新记录到数据库"""
        date = date_input.date().toString("yyyy-MM-dd")
        try:
            amount = float(amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return

        currency = currency_combobox.currentText()
        type_ = type_combobox.currentText()
        category = category_combobox.currentText()
        note = note_input.text()

        self.cursor.execute("UPDATE records SET date=?, amount=?, currency=?, type=?, category=?, note=? WHERE id=?",
                            (date, amount, currency, type_, category, note, record_id))
        self.conn.commit()
        self.load_records()
        dialog.close()

    def style_sheet(self):
        """返回 QSS 样式表"""
        return """
            /* 侧边栏按钮样式 */
            QPushButton {
                border: 2px solid #8f8f91;
                border-radius: 6px;
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                  stop: 0 #f6f7fa, stop: 1 #dadbde);
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #2980b9;
            }

            QPushButton:pressed {
                background-color: #2c3e50;
            }

            /* 其他样式保持不变 */
            QWidget {
                background-color: #f0f0f0;
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

            QLabel {
                color: #333333;
                font-size: 14px;
            }

            QMessageBox {
                background-color: #f0f0f0;
                color: #333333;
            }
        """


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AccountingApp()
    ex.show()
    sys.exit(app.exec_())

import os
import sys
import platform
import time
import sqlite3
import csv
import json
import base64
import hashlib
import vosk
import pyaudio
import wave
import jieba
import re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asymmetric_padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView, QSizePolicy, QTextEdit, QListWidget, 
    QListWidgetItem, QStackedWidget, QColorDialog, QCheckBox, QFileDialog, QSlider, 
    QTabWidget, QInputDialog, QGroupBox, QKeySequenceEdit, QFrame, QStatusBar, QSplitter,
    QTabBar, QToolButton, QSpacerItem
)
from PySide6.QtCore import QDate, Qt, QTimer, Signal, QThread, QSettings, QSize, QUrl
from PySide6.QtGui import QIcon, QPixmap, QKeySequence, QFont, QPalette, QColor, QLinearGradient, QBrush, QPainter, QCursor, QShortcut


# 资源路径处理函数
def resource_path(relative_path):
    """获取资源文件的绝对路径，适用于PyInstaller打包后的程序"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 语音识别线程类
class VoiceRecognition(QThread):
    recognized_text = Signal(str)
    recording_stopped = Signal()
    
    def __init__(self, model_path="resources/vosk-model-small-cn-0.22", timeout=20):
        super().__init__()
        self.model_path = model_path
        self.is_recording = False
        self._stop_requested = False  # 停止请求标志
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
            
            while self.is_recording and not self._stop_requested:
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
                
                if self._stop_requested:
                    break
            
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
            self._stop_requested = True
            
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                
            if self.p:
                self.p.terminate()
                
            self.quit()
            self.wait()
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


# 加密管理类
class EncryptionManager:
    def __init__(self):
        self.salt = os.urandom(16)
        self.iterations = 100000
        self.block_size = algorithms.AES.block_size
        
    def generate_rsa_key_pair(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        return private_key, public_key
        
    def derive_aes_key(self, password):
        kdf = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            self.salt,
            self.iterations
        )
        return kdf
        
    def encrypt_data(self, data, aes_key, public_key):
        iv = os.urandom(self.block_size // 8)
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(self.block_size).padder()
        padded_data = padder.update(data) + padder.finalize()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        rsa_cipher = public_key.encrypt(
            aes_key,
            asymmetric_padding.OAEP(
                mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return {
            'salt': base64.b64encode(self.salt).decode('utf-8'),
            'iterations': self.iterations,
            'iv': base64.b64encode(iv).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'encrypted_aes_key': base64.b64encode(rsa_cipher).decode('utf-8'),
            'rsa_public_key': base64.b64encode(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )).decode('utf-8')
        }
        
    def decrypt_data(self, encrypted_data, password, private_key):
        try:
            salt = base64.b64decode(encrypted_data['salt'])
            iterations = encrypted_data['iterations']
            iv = base64.b64decode(encrypted_data['iv'])
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            encrypted_aes_key = base64.b64decode(encrypted_data['encrypted_aes_key'])
            rsa_public_key = base64.b64decode(encrypted_data['rsa_public_key'])
            
            kdf = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                iterations
            )
            
            decrypted_aes_key = private_key.decrypt(
                encrypted_aes_key,
                asymmetric_padding.OAEP(
                    mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            if decrypted_aes_key != kdf:
                raise ValueError("密码错误或密钥不匹配")
                
            cipher = Cipher(algorithms.AES(decrypted_aes_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = padding.PKCS7(self.block_size).unpadder()
            plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
            
            return plaintext
            
        except Exception as e:
            print(f"解密失败: {e}")
            return None


# 文件管理类
class FileManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.encryption_manager = EncryptionManager()
        self.private_key = None
        self.public_key = None
        
    def create_encrypted_file(self, password, data):
        self.private_key, self.public_key = self.encryption_manager.generate_rsa_key_pair()
        aes_key = self.encryption_manager.derive_aes_key(password)
        encrypted_data = self.encryption_manager.encrypt_data(data, aes_key, self.public_key)
        
        with open(self.file_path, 'w') as f:
            json.dump(encrypted_data, f)
            
        # 保存私钥到文件
        with open("private_key.pem", "wb") as key_file:
            key_file.write(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )
            
        return True
        
    def read_encrypted_file(self, password):
        try:
            with open(self.file_path, 'r') as f:
                encrypted_data = json.load(f)
                
            # 从文件中加载私钥
            if self.private_key is None:
                with open("private_key.pem", "rb") as key_file:
                    self.private_key = serialization.load_pem_private_key(
                        key_file.read(),
                        password=None,
                        backend=default_backend()
                    )
                    
            decrypted_data = self.encryption_manager.decrypt_data(encrypted_data, password, self.private_key)
            return decrypted_data
            
        except Exception as e:
            print(f"读取加密文件失败: {e}")
            return None
            
    def export_to_csv(self, db_path, file_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM records")
        records = cursor.fetchall()
        conn.close()
        
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['id', 'date', 'amount', 'currency', 'type', 'category', 'note'])
            for record in records:
                writer.writerow(record)
                
        return True
        
    def import_from_csv(self, db_path, file_path):
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                next(reader)  # 跳过表头
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM records")
                
                for row in reader:
                    cursor.execute(
                        "INSERT INTO records (id, date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?,?)",
                        tuple(row)
                    )
                    
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"导入CSV文件失败: {e}")
            return False
            
    def export_to_jzrj(self, db_path, original_file_name, password):
        try:
            # 导出CSV文件
            csv_file_name = f"{original_file_name}.csv"
            if not self.export_to_csv(db_path, csv_file_name):
                return False
                
            # 读取CSV文件内容
            with open(csv_file_name, 'r', encoding='utf-8') as f:
                csv_data = f.read().encode('utf-8')
                
            # 生成RSA密钥对
            private_key, public_key = self.encryption_manager.generate_rsa_key_pair()
            
            # 生成AES密钥
            aes_key = self.encryption_manager.derive_aes_key(password)
            
            # 加密CSV数据
            encrypted_data = self.encryption_manager.encrypt_data(csv_data, aes_key, public_key)
            
            # 创建.jzrj文件
            jzrj_file_name = f"{original_file_name}.jzrj"
            with open(jzrj_file_name, 'w') as f:
                json.dump(encrypted_data, f)
                
            # 计算哈希值
            with open(jzrj_file_name, 'rb') as f:
                jzrj_data = f.read()
                
            hash_value = hashlib.sha256(jzrj_data).hexdigest()
            
            # 创建哈希值文件
            hash_file_name = f"{original_file_name}.jzrj.hash"
            with open(hash_file_name, 'w') as f:
                f.write(hash_value)
                
            # 删除临时CSV文件
            os.remove(csv_file_name)
            
            # 保存私钥到文件
            with open("private_key.pem", "wb") as key_file:
                key_file.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption()
                    )
                )
                
            return True
            
        except Exception as e:
            print(f"导出到.jzrj文件时出错: {e}")
            return False
            
    def import_from_jzrj(self, jzrj_file_path, password):
        try:
            # 检查文件是否存在
            if not os.path.exists(jzrj_file_path):
                print(f"文件不存在: {jzrj_file_path}")
                return False
                
            # 提取原始文件名
            original_file_name = os.path.splitext(jzrj_file_path)[0]
            
            # 检查哈希值文件是否存在
            hash_file_name = f"{original_file_name}.jzrj.hash"
            if not os.path.exists(hash_file_name):
                print(f"哈希值文件不存在: {hash_file_name}")
                return False
                
            # 读取文件Hash值
            with open(hash_file_name, 'r') as f:
                expected_hash = f.read().strip()
                
            # 计算当前文件的哈希值
            with open(jzrj_file_path, 'rb') as f:
                jzrj_data = f.read()
                
            current_hash = hashlib.sha256(jzrj_data).hexdigest()
            
            # 验证哈希值
            if current_hash != expected_hash:
                print(f"哈希值不匹配，文件可能被篡改！")
                return False
                
            # 读取加密数据
            encrypted_data = json.loads(jzrj_data.decode('utf-8'))
            
            # 从文件中加载私钥
            if self.private_key is None:
                with open("private_key.pem", "rb") as key_file:
                    self.private_key = serialization.load_pem_private_key(
                        key_file.read(),
                        password=None,
                        backend=default_backend()
                    )
                    
            # 解密数据
            decrypted_data = self.encryption_manager.decrypt_data(encrypted_data, password, self.private_key)
            if not decrypted_data:
                return False
                
            # 将解密后的数据写入CSV文件
            csv_file_name = f"{original_file_name}.csv"
            with open(csv_file_name, 'w', encoding='utf-8') as f:
                f.write(decrypted_data.decode('utf-8'))
                
            # 导入CSV文件到数据库
            db_path = 'accounting.db'
            if not self.import_from_csv(db_path, csv_file_name):
                return False
                
            # 删除临时CSV文件
            os.remove(csv_file_name)
            return True
            
        except Exception as e:
            print(f"从.jzrj文件导入时出错: {e}")
            return False


# 自定义对话框基类，确保所有对话框符合主题
class ThemedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f2f5;
                font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
            }
            QLabel {
                color: #2d3949;
                font-size: 14px;
            }
            QPushButton {
                background-color: #3a7bd5;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4a8be5;
            }
            QPushButton:pressed {
                background-color: #2a6bc5;
            }
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 6px 8px;
                background-color: white;
                color: #2d3949;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border-color: #3a7bd5;
                outline: none;
            }
        """)


# 录音对话框
class RecordDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("录音")
        self.setFixedSize(300, 180)
        
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("准备录音...", alignment=Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.time_label = QLabel("00:00", alignment=Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 24px; margin: 15px 0;")
        
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        
        layout.addWidget(self.status_label)
        layout.addWidget(self.time_label)
        layout.addLayout(button_layout)
        
        # 绑定录音逻辑
        self.start_btn.clicked.connect(self.start_recording)
        self.stop_btn.clicked.connect(self.stop_recording)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.elapsed_time = 0
        self.voice_thread = None

    def start_recording(self):
        # 调用录音逻辑
        model_path = resource_path("resources/vosk-model-small-cn-0.22")
        self.voice_thread = VoiceRecognition(model_path, 20)
        self.voice_thread.recognized_text.connect(self.parent_app.process_voice_input)
        self.voice_thread.recording_stopped.connect(self.handle_recording_stopped)
        self.voice_thread.start()
        
        self.status_label.setText("正在录音...")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.elapsed_time = 0
        self.timer.start(1000)
        
    def stop_recording(self):
        # 停止录音
        if self.voice_thread and self.voice_thread.isRunning():
            self.voice_thread.stop_recording()
        
    def handle_recording_stopped(self):
        self.status_label.setText("录音已停止")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.timer.stop()
        
    def update_time(self):
        self.elapsed_time += 1
        minutes = self.elapsed_time // 60
        seconds = self.elapsed_time % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")


# 添加记录对话框
class AddRecordDialog(ThemedDialog):
    def __init__(self, parent=None, is_modify=False, record_id=None):
        super().__init__(parent)
        self.parent_app = parent
        self.is_modify = is_modify
        self.record_id = record_id
        
        if is_modify:
            self.setWindowTitle('修改记录')
        else:
            self.setWindowTitle('添加账本')
            
        self.init_ui()
        
        # 如果是修改，加载现有数据
        if is_modify and record_id:
            self.load_record_data()
            
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        date_layout = QHBoxLayout()
        date_label = QLabel("日期:")
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_input)
        
        amount_layout = QHBoxLayout()
        amount_label = QLabel("金额:")
        self.amount_input = QLineEdit()
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(self.amount_input)
        
        currency_layout = QHBoxLayout()
        currency_label = QLabel("币种:")
        self.currency_combobox = QComboBox()
        self.currency_combobox.addItems(["人民币 (CNY)", "美元 (USD)", "欧元 (EUR)", "日元 (JPY)", "其他"])
        currency_layout.addWidget(currency_label)
        currency_layout.addWidget(self.currency_combobox)
        
        type_layout = QHBoxLayout()
        type_label = QLabel("收支类型:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["收入", "支出"])
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combobox)
        
        category_layout = QHBoxLayout()
        category_label = QLabel("详细分类:")
        self.category_combobox = QComboBox()
        income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
        expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
        self.category_combobox.addItems(income_categories + expense_categories)
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combobox)
        
        note_layout = QHBoxLayout()
        note_label = QLabel("备注信息:")
        self.note_input = QLineEdit()
        note_layout.addWidget(note_label)
        note_layout.addWidget(self.note_input)
        
        button_layout = QHBoxLayout()
        if self.is_modify:
            self.confirm_btn = QPushButton("修改记录")
            self.confirm_btn.clicked.connect(self.modify_record)
        else:
            self.confirm_btn = QPushButton("添加记录")
            self.confirm_btn.clicked.connect(self.add_record)
            
        button_layout.addWidget(self.confirm_btn)
        
        layout.addLayout(date_layout)
        layout.addLayout(amount_layout)
        layout.addLayout(currency_layout)
        layout.addLayout(type_layout)
        layout.addLayout(category_layout)
        layout.addLayout(note_layout)
        layout.addLayout(button_layout)
        
        self.setFixedSize(400, 300)
        
    def load_record_data(self):
        # 从数据库加载记录数据
        self.parent_app.cursor.execute("SELECT * FROM records WHERE id=?", (self.record_id,))
        record = self.parent_app.cursor.fetchone()
        
        if record:
            self.date_input.setDate(QDate.fromString(record[1], "yyyy-MM-dd"))
            self.amount_input.setText(str(record[2]))
            self.currency_combobox.setCurrentText(record[3])
            self.type_combobox.setCurrentText(record[4])
            self.category_combobox.setCurrentText(record[5])
            self.note_input.setText(record[6])
            
    def add_record(self):
        try:
            amount = float(self.amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return
            
        self.parent_app.cursor.execute(
            "INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
            (self.date_input.date().toString("yyyy-MM-dd"),
             amount,
             self.currency_combobox.currentText(),
             self.type_combobox.currentText(),
             self.category_combobox.currentText(),
             self.note_input.text())
        )
        
        self.parent_app.conn.commit()
        self.parent_app.load_records()
        self.accept()
        
    def modify_record(self):
        try:
            amount = float(self.amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return
            
        self.parent_app.cursor.execute(
            "UPDATE records SET date=?, amount=?, currency=?, type=?, category=?, note=? WHERE id=?",
            (self.date_input.date().toString("yyyy-MM-dd"),
             amount,
             self.currency_combobox.currentText(),
             self.type_combobox.currentText(),
             self.category_combobox.currentText(),
             self.note_input.text(),
             self.record_id)
        )
        
        self.parent_app.conn.commit()
        self.parent_app.load_records()
        self.accept()


# 设置对话框
class SettingsDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("设置")
        self.setFixedSize(600, 400)
        
        self.file_manager = FileManager("accounting.jzrj")
        
        main_layout = QHBoxLayout(self)
        
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
                border-left: 3px solid #3a7bd5;
                color: #3a7bd5;
            }
        """)
        
        menu_items = ["用户协议", "文件管理", "文件加密", "关于"]
        for item in menu_items:
            self.menu_list.addItem(item)
            
        self.menu_list.setCurrentRow(4)  # 默认选中“关于”
        
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("""
            background-color: white;
            border-left: 1px solid #eee;
        """)
        
        self.create_pages()
        
        self.menu_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        
        main_layout.addWidget(self.menu_list)
        main_layout.addWidget(self.stacked_widget)
        
    def create_pages(self):
        """创建所有页面并添加到堆叠窗口"""
        self.add_menu_page("用户协议", self.create_user_agreement_page())
        self.add_menu_page("文件管理", self.create_file_management_page())
        self.add_menu_page("文件加密", self.create_file_encryption_page())
        self.add_menu_page("关于", self.create_about_page())
        
    def add_menu_page(self, title, widget):
        """将页面添加到堆叠窗口"""
        self.stacked_widget.addWidget(widget)
        
    def create_user_agreement_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        agreement_label = QLabel("用户协议")
        agreement_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(agreement_label)
        
        self.agreement_text = QTextEdit()
        self.agreement_text.setReadOnly(True)
        self.agreement_text.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #333;")
        self.load_user_agreement()
        
        layout.addWidget(self.agreement_text)
        layout.addStretch()
        
        return page
        
    def create_file_management_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
    
        export_import_group = QGroupBox("数据导出/导入")
        export_import_layout = QVBoxLayout()
    
        self.export_button = QPushButton("导出到CSV文件")
        self.export_button.clicked.connect(self.export_to_csv)
        export_import_layout.addWidget(self.export_button)
    
        self.import_button = QPushButton("从CSV文件导入")
        self.import_button.clicked.connect(self.import_from_csv)
        export_import_layout.addWidget(self.import_button)
    
        export_import_group.setLayout(export_import_layout)
        layout.addWidget(export_import_group)
        layout.addStretch()
    
        return page
        
    def create_file_encryption_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        encryption_group = QGroupBox("文件加密")
        encryption_layout = QVBoxLayout()
        
        self.encrypt_button = QPushButton("加密导出为.jzrj文件")
        self.encrypt_button.clicked.connect(self.encrypt_and_export)
        encryption_layout.addWidget(self.encrypt_button)
        
        self.decrypt_button = QPushButton("从.jzrj文件解密导入")
        self.decrypt_button.clicked.connect(self.decrypt_and_import)
        encryption_layout.addWidget(self.decrypt_button)
        
        encryption_group.setLayout(encryption_layout)
        layout.addWidget(encryption_group)
        layout.addStretch()
        
        return page
        

    def create_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        version_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap(resource_path('resources/app.png'))
        icon_label.setPixmap(pixmap.scaled(64, 64, Qt.IgnoreAspectRatio))
        version_layout.addWidget(icon_label)
        
        version_label = QLabel("使用条款、版权声明与开源协议")
        version_label.setStyleSheet("font-size: 18px; color: #333;")
        version_layout.addWidget(version_label)
        version_layout.addStretch()
        
        layout.addLayout(version_layout)
        
        # 加载许可证信息
        self.mit_license_zh_cn_label = QTextEdit()
        self.mit_license_zh_cn_label.setReadOnly(True)
        self.mit_license_zh_cn_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        self.load_text_file(resource_path(os.path.join("license", "MIT_License_ZH-CN.txt")), self.mit_license_zh_cn_label)
        layout.addWidget(self.mit_license_zh_cn_label)
        
        layout.addStretch()
        
        return page
        
    def load_text_file(self, file_path, text_edit):
        """加载文本文件内容到指定的 QTextEdit 控件中"""
        try:
            full_path = resource_path(file_path)
            with open(full_path, 'r', encoding='utf-8') as file:
                content = file.read()
                text_edit.setText(content)
        except Exception as e:
            text_edit.setText(f"无法加载文件：{file_path}\n错误信息：{str(e)}")
            print(f"无法加载文件：{file_path}\n错误信息：{str(e)}")
            
    def load_user_agreement(self):
        """加载用户协议文件内容"""
        try:
            file_path = resource_path(os.path.join("license", "user_agreement.txt"))
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                self.agreement_text.setText(content)
        except Exception as e:
            self.agreement_text.setText(f"无法加载用户协议文件：{file_path}\n错误信息：{str(e)}")
            
    def export_to_csv(self):
        """导出数据到 CSV 文件"""
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("导出到CSV文件")
            file_dialog.setLabelText(QFileDialog.Accept, "保存")
            file_dialog.setNameFilter("CSV文件 (*.csv)")
            file_dialog.setDefaultSuffix("csv")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            
            if file_dialog.exec():
                file_path = file_dialog.selectedFiles()[0]
                if self.file_manager.export_to_csv("accounting.db", file_path):
                    QMessageBox.information(self, "导出成功", f"数据已成功导出到: {file_path}")
                else:
                    QMessageBox.warning(self, "导出失败", "导出数据时发生错误！")
                    
        except Exception as e:
            print(f"导出数据时出错: {e}")
            QMessageBox.critical(self, "错误", f"导出数据时出错: {str(e)}")
            
    def import_from_csv(self):
        """从 CSV 文件导入数据"""
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("从CSV文件导入")
            file_dialog.setLabelText(QFileDialog.Accept, "打开")
            file_dialog.setNameFilter("CSV文件 (*.csv)")
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            
            if file_dialog.exec():
                file_path = file_dialog.selectedFiles()[0]
                if self.file_manager.import_from_csv("accounting.db", file_path):
                    QMessageBox.information(self, "导入成功", f"数据已成功从: {file_path} 导入")
                    self.parent_app.load_records()  # 刷新记录
                else:
                    QMessageBox.warning(self, "导入失败", "导入数据时发生错误！")
                    
        except Exception as e:
            print(f"导入数据时出错: {e}")
            QMessageBox.critical(self, "错误", f"导入数据时出错: {str(e)}")
            
    def encrypt_and_export(self):
        """加密导出为.jzrj文件"""
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("加密导出为.jzrj文件")
            file_dialog.setLabelText(QFileDialog.Accept, "保存")
            file_dialog.setNameFilter("JZRJ文件 (*.jzrj)")
            file_dialog.setDefaultSuffix("jzrj")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            
            if file_dialog.exec():
                file_path = file_dialog.selectedFiles()[0]
                original_file_name = os.path.splitext(file_path)[0]
                
                password, ok = QInputDialog.getText(self, "输入密码", "请输入加密密码:", QLineEdit.Password)
                if ok and password:
                    if self.file_manager.export_to_jzrj("accounting.db", original_file_name, password):
                        QMessageBox.information(self, "加密导出成功", f"数据已成功加密导出到: {file_path}")
                    else:
                        QMessageBox.warning(self, "加密导出失败", "加密导出时发生错误！")
                        
        except Exception as e:
            print(f"加密导出时出错: {e}")
            QMessageBox.critical(self, "错误", f"加密导出时出错: {str(e)}")
            
    def decrypt_and_import(self):
        """从.jzrj文件解密导入"""
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("从.jzrj文件解密导入")
            file_dialog.setLabelText(QFileDialog.Accept, "打开")
            file_dialog.setNameFilter("JZRJ文件 (*.jzrj)")
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            
            if file_dialog.exec():
                file_path = file_dialog.selectedFiles()[0]
                
                password, ok = QInputDialog.getText(self, "输入密码", "请输入解密密码:", QLineEdit.Password)
                if ok and password:
                    if self.file_manager.import_from_jzrj(file_path, password):
                        QMessageBox.information(self, "解密导入成功", f"数据已成功从: {file_path} 解密导入")
                        self.parent_app.load_records()  # 刷新记录
                    else:
                        QMessageBox.warning(self, "解密导入失败", "解密导入时发生错误！")
                        
        except Exception as e:
            print(f"解密导入时出错: {e}")
            QMessageBox.critical(self, "错误", f"解密导入时出错: {str(e)}")


# 关于对话框
class AboutDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setFixedSize(350, 250)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # 软件图标
        icon_label = QLabel()
        icon_label.setPixmap(QPixmap(resource_path("resources/app.png")).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.setAlignment(Qt.AlignCenter)
        
        # 软件名称和版本
        name_label = QLabel("PennAicoin 锦云策")
        name_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px 0;")
        name_label.setAlignment(Qt.AlignCenter)
        
        version_label = QLabel("版本: V0.1.1.2025.07.24_01_RC")
        version_label.setAlignment(Qt.AlignCenter)
        
        # 开发者信息
        dev_label = QLabel("开发者: wuhuang2")
        dev_label.setAlignment(Qt.AlignCenter)
        
        # 版权信息
        copyright_label = QLabel("© 2025 wuhuang2@github 保留所有权利")
        copyright_label.setStyleSheet("font-size: 12px; color: #666; margin-top: 20px;")
        copyright_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(icon_label)
        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(dev_label)
        layout.addWidget(copyright_label)
        
        # 确定按钮
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setFixedWidth(100)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)


# 解密对话框
class DecryptDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("解密文件")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("请输入解密密码:"))
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)
        
        btn_layout = QHBoxLayout()
        decrypt_btn = QPushButton("解密")
        cancel_btn = QPushButton("取消")
        
        btn_layout.addWidget(decrypt_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        # 绑定解密逻辑
        decrypt_btn.clicked.connect(self.decrypt)
        cancel_btn.clicked.connect(self.reject)
        
        self.decrypted_data = None
        
    def decrypt(self):
        password = self.password_input.text()
        if not password:
            QMessageBox.warning(self, "警告", "请输入密码")
            return
            
        # 这里可以调用实际解密逻辑
        self.decrypted_data = "解密后的数据"  # 替换为真实解密数据
        self.accept()


# 主窗口类
class PennAicoinMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.current_user = "admin"  # 默认登录为“Admin”
        self.voice_thread = None
        self.password_enabled = False
        self.shortcuts = {}
        
        # 初始化数据库
        self.init_db()
        
        # 窗口基本设置
        self.setWindowTitle("PennAicoin 锦云策")
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowIcon(QIcon(resource_path('resources/user.ico')))
        
        # 创建主布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 创建左侧导航栏
        self.create_left_navigation()
        
        # 创建顶部导航栏和标签页
        self.create_top_navigation()
        
        # 创建主内容区域
        self.create_main_content()
        
        # 初始化显示主页
        self.show_home_page()
        
        # 应用全局样式
        self.apply_styles()
        
        # 初始化定时器
        self.init_timer()
        
        # 加载记录
        self.load_records()

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
        
    def init_timer(self):
        """初始化定时器"""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.load_records)  # 每分钟刷新一次
        self.update_timer.start(60000)
        
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)
        self.update_time()
        


    def apply_styles(self):
        """应用全局样式表"""
        self.setStyleSheet("""
            /* 主窗口样式 */
            QMainWindow {
                background-color: #f0f2f5;
            }
            
            /* 左侧导航栏样式 */
            #leftNavigation {
                background-color: #FFFFFF;
                border: none;
            }
            
            /* 导航按钮样式 */
            .navButton {
                background-color: transparent;
                border: none;
                padding: 10px;
                margin: 5px 0;
                border-radius: 6px;
            }
            
            .navButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            
            .navButton:pressed, .navButton:checked {
                background-color: rgba(255, 255, 255, 0.2);
            }
            
            /* 顶部导航栏样式 */
            #topNavigation {
                background-color: white;
                border-bottom: 1px solid #e1e4e8;
                padding: 0 15px;
            }
            
            /* 软件名称样式 */
            #appNameLabel {
                color: #2d3949;
                font-size: 16px;
                font-weight: bold;
                font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
                margin-left: 10px;
            }
            
            /* 搜索框样式 */
            #searchBox {
                border: 1px solid #d0d7de;
                border-radius: 16px;
                padding: 5px 12px;
                background-color: #f6f8fa;
                width: 200px;
            }
            
            #searchBox:focus {
                background-color: white;
                border-color: #3a7bd5;
                outline: none;
            }
            
            /* 标签页样式 */
            QTabWidget::pane {
                border: none;
                background-color: #f0f2f5;
            }
            
            QTabBar::tab {
                background-color: #f0f2f5;
                color: #666;
                padding: 8px 16px;
                border-radius: 4px 4px 0 0;
                margin-right: 2px;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                color: #2d3949;
                border-top: 2px solid #3a7bd5;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #eaecef;
            }
            
            /* 表格样式 */
            QTableWidget {
                background-color: white;
                border: 1px solid #e1e4e8;
                border-radius: 4px;
                gridline-color: #e1e4e8;
                font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
            }
            
            QTableWidget::item {
                padding: 6px;
                border: none;
            }
            
            QTableWidget::item:selected {
                background-color: #e8f0fe;
                color: #2d3949;
            }
            
            QHeaderView::section {
                background-color: #f6f8fa;
                color: #666;
                padding: 8px;
                border: 1px solid #e1e4e8;
                text-align: left;
            }
            
            /* 账本操作按钮样式 */
            #createBtn {
                background-color: white;
                color: #2d3949;
                border: 1px solid #c2e0c6;
                padding: 6px 16px;
                border-radius: 4px;
                margin-right: 8px;
            }
            
            #createBtn:hover, #createBtn:pressed {
                background-color: #c2e0c6;
                color: #137333;
            }
            
            #deleteBtn {
                background-color: white;
                color: #2d3949;
                border: 1px solid #f8d7da;
                padding: 6px 16px;
                border-radius: 4px;
                margin-right: 8px;
            }
            
            #deleteBtn:hover, #deleteBtn:pressed {
                background-color: #f8d7da;
                color: #c82333;
            }
            
            #modifyBtn {
                background-color: white;
                color: #2d3949;
                border: 1px solid #ffeeba;
                padding: 6px 16px;
                border-radius: 4px;
            }
            
            #modifyBtn:hover, #modifyBtn:pressed {
                background-color: #ffeeba;
                color: #856404;
            }
        """)

    def create_left_navigation(self):
        """创建左侧导航栏"""
        self.left_nav = QWidget()
        self.left_nav.setObjectName("leftNavigation")
        self.left_nav.setFixedWidth(60)  # 窄版导航栏
        
        layout = QVBoxLayout(self.left_nav)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.setContentsMargins(5, 15, 5, 15)
        layout.setSpacing(10)
        
        # 预留软件图标位置
        app_icon = QLabel()
        app_icon.setPixmap(QPixmap(resource_path("resources/app.png")).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        app_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(app_icon)
        
        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.1); height: 1px; margin: 10px 0;")
        layout.addWidget(line)
        
        # 导航按钮 - 主页
        self.home_btn = QPushButton()
        self.home_btn.setObjectName("homeBtn")
        self.home_btn.setProperty("class", "navButton")
        self.home_btn.setFixedSize(40, 40)
        self.home_btn.setIcon(QIcon(resource_path("resources/home.ico")))
        self.home_btn.setIconSize(QSize(24, 24))
        self.home_btn.setCheckable(True)
        self.home_btn.setChecked(True)
        self.home_btn.clicked.connect(self.show_home_page)
        layout.addWidget(self.home_btn)
        
        # 导航按钮 - 开始录音
        self.record_btn = QPushButton()
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.setProperty("class", "navButton")
        self.record_btn.setFixedSize(40, 40)
        self.record_btn.setIcon(QIcon(resource_path("resources/voice.ico")))
        self.record_btn.setIconSize(QSize(24, 24))
        self.record_btn.clicked.connect(self.show_record_dialog)
        layout.addWidget(self.record_btn)
        
        # 导航按钮 - 设置
        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setProperty("class", "navButton")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.setIcon(QIcon(resource_path("resources/settings.ico")))
        self.settings_btn.setIconSize(QSize(24, 24))
        self.settings_btn.clicked.connect(self.show_settings_dialog)
        layout.addWidget(self.settings_btn)
        
        # 导航按钮 - 关于
        self.about_btn = QPushButton()
        self.about_btn.setObjectName("aboutBtn")
        self.about_btn.setProperty("class", "navButton")
        self.about_btn.setFixedSize(40, 40)
        self.about_btn.setIcon(QIcon(resource_path("resources/info.ico")))
        self.about_btn.setIconSize(QSize(24, 24))
        self.about_btn.clicked.connect(self.show_about_dialog)
        layout.addWidget(self.about_btn)
        
        # 添加伸缩项，将按钮推到顶部
        layout.addStretch()
        
        # 将左侧导航添加到主布局
        self.main_layout.addWidget(self.left_nav)

    def create_top_navigation(self):
        """创建顶部导航栏和多标签页"""
        # 右侧主容器
        self.right_container = QWidget()
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # 顶部导航栏
        self.top_nav = QWidget()
        self.top_nav.setObjectName("topNavigation")
        self.top_nav.setFixedHeight(50)
        
        top_layout = QHBoxLayout(self.top_nav)
        top_layout.setContentsMargins(0, 0, 10, 0)
        top_layout.setSpacing(10)
        
        # 软件名称
        self.app_name = QLabel("PennAicoin 锦云策")
        self.app_name.setObjectName("appNameLabel")
        top_layout.addWidget(self.app_name)
        
        # 伸缩项
        top_layout.addStretch()
        
        # 搜索框
        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("搜索...")
        top_layout.addWidget(self.search_box)
        
    
        
        # 添加顶部导航到右侧容器
        right_layout.addWidget(self.top_nav)
        
        # 创建多标签页控件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        # 添加默认的空白标签页
        self.add_new_tab("欢迎使用", "welcome")
        
        right_layout.addWidget(self.tab_widget)
        
        # 将右侧容器添加到主布局
        self.main_layout.addWidget(self.right_container, 1)

    def show_export_prompt(self):
        """显示导出提示并调用设置对话框中的导出功能"""
        dialog = SettingsDialog(self)
        dialog.export_to_csv()  # 直接调用导出功能

    def show_import_prompt(self):
        """显示导入提示并调用设置对话框中的导入功能"""
        dialog = SettingsDialog(self)
        dialog.import_from_csv()  # 直接调用导入功能

    def create_main_content(self):
        """创建主内容区域"""
        # 主页内容
        self.home_page = QWidget()
        home_layout = QVBoxLayout(self.home_page)
        home_layout.setContentsMargins(20, 20, 20, 20)
        home_layout.setSpacing(15)
        
        # 账本操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignLeft)
        
        self.create_btn = QPushButton("创建账本")
        self.create_btn.setObjectName("createBtn")
        self.create_btn.clicked.connect(self.show_add_dialog)
        
        self.delete_btn = QPushButton("删除账本")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.clicked.connect(self.delete_record)
        
        self.modify_btn = QPushButton("修改账本")
        self.modify_btn.setObjectName("modifyBtn")
        self.modify_btn.clicked.connect(self.modify_record)
        
        btn_layout.addWidget(self.create_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.modify_btn)
        btn_layout.addStretch()
        
        home_layout.addLayout(btn_layout)
        
        # 表格控件
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(6)
        self.table_widget.setHorizontalHeaderLabels(["日期", "金额", "币种", "收支类型", "详细分类", "备注信息"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        home_layout.addWidget(self.table_widget)

    def load_records(self):
        """从数据库加载记录并更新表格"""
        self.cursor.execute("SELECT * FROM records")
        records = self.cursor.fetchall()
        
        # 更新表格
        self.table_widget.setRowCount(len(records))
        for row, record in enumerate(records):
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])  # 存储ID
            self.table_widget.setItem(row, 0, date_item)
            self.table_widget.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table_widget.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table_widget.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table_widget.setItem(row, 4, QTableWidgetItem(record[5]))
            self.table_widget.setItem(row, 5, QTableWidgetItem(record[6]))

    def update_time(self):
        """更新时间显示"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.app_name.setText(f"PennAicoin 锦云策  |  {current_time}")

    def show_home_page(self):
        """显示主页内容"""
        # 更新导航按钮状态
        self.home_btn.setChecked(True)
        self.record_btn.setChecked(False)
        self.settings_btn.setChecked(False)
        self.about_btn.setChecked(False)
        
        # 在标签页中显示主页内容
        home_tab_index = -1
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "主页":
                home_tab_index = i
                break
                
        if home_tab_index != -1:
            self.tab_widget.setCurrentIndex(home_tab_index)
        else:
            self.tab_widget.addTab(self.home_page, "主页")
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def show_record_dialog(self):
        """显示录音对话框"""
        # 保持主页显示，只弹出对话框
        self.home_btn.setChecked(True)
        self.record_btn.setChecked(False)
        self.settings_btn.setChecked(False)
        self.about_btn.setChecked(False)
        
        dialog = RecordDialog(self)
        dialog.exec()

    def show_settings_dialog(self):
        """显示设置对话框"""
        # 保持主页显示，只弹出对话框
        self.home_btn.setChecked(True)
        self.record_btn.setChecked(False)
        self.settings_btn.setChecked(False)
        self.about_btn.setChecked(False)
        
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_about_dialog(self):
        """显示关于对话框"""
        # 保持主页显示，只弹出对话框
        self.home_btn.setChecked(True)
        self.record_btn.setChecked(False)
        self.settings_btn.setChecked(False)
        self.about_btn.setChecked(False)
        
        dialog = AboutDialog(self)
        dialog.exec()

    def show_add_dialog(self):
        """显示添加记录对话框"""
        dialog = AddRecordDialog(self)
        dialog.exec()

    def modify_record(self):
        """修改选中的记录"""
        selected_row = self.table_widget.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return
            
        item = self.table_widget.item(selected_row, 0)
        if item is None:
            QMessageBox.warning(self, "错误", "无法获取记录的 ID！")
            return
            
        record_id = item.data(Qt.UserRole)
        dialog = AddRecordDialog(self, is_modify=True, record_id=record_id)
        dialog.exec()

    def delete_record(self):
        """删除选中的记录"""
        selected_row = self.table_widget.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return
            
        item = self.table_widget.item(selected_row, 0)
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

    def process_voice_input(self, recognized_text):
        """处理语音输入"""
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
            
            # 显示识别结果并添加记录
            QMessageBox.information(self, "语音识别结果", 
                                   f"识别内容: {recognized_text}\n\n"
                                   f"将添加记录:\n"
                                   f"日期: {date}\n"
                                   f"金额: {amount}\n"
                                   f"币种: {currency}\n"
                                   f"类型: {type_}\n"
                                   f"分类: {category}")
            
            self.add_record(date, amount, currency, type_, category, note)
        else:
            print("未识别到有效内容")
            QMessageBox.warning(self, "语音识别", "未识别到有效内容")

    def extract_date(self, words):
        """从语音中提取日期"""
        date_pattern = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日')
        for word in words:
            if date_pattern.match(word):
                return word.replace('年', '-').replace('月', '-').replace('日', '')
        return QDate.currentDate().toString("yyyy-MM-dd")

    def extract_amount(self, words):
        """从语音中提取金额"""
        amount_pattern = re.compile(r'\d+\.?\d*')
        for word in words:
            match = amount_pattern.findall(word)
            if match:
                return float(match[0])
        return 0.0

    def extract_currency(self, words):
        """从语音中提取币种"""
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
        """从语音中提取收支类型"""
        if '收入' in words:
            return '收入'
        elif '支出' in words:
            return '支出'
        else:
            return '支出'

    def extract_category(self, words):
        """从语音中提取分类"""
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
        """从语音中提取备注"""
        return ' '.join(words)

    def add_record(self, date, amount, currency, type_, category, note):
        """添加记录到数据库"""
        print("添加记录到数据库...")
        try:
            self.cursor.execute(
                "INSERT INTO records (date, amount, currency, type, category, note) VALUES (?,?,?,?,?,?)",
                (date, amount, currency, type_, category, note)
            )
            self.conn.commit()
            self.load_records()
        except Exception as e:
            print(f"添加记录时出错: {str(e)}")

    def add_new_tab(self, title, file_type=None, file_path=None):
        """添加新的标签页"""
        # 创建标签页内容
        tab_content = QWidget()
        layout = QVBoxLayout(tab_content)
        
        if title == "欢迎使用":
            welcome_label = QLabel("欢迎使用PennAicoin 锦云策\n\n请使用左侧导航栏访问不同功能，或打开一个文件开始工作。")
            welcome_label.setStyleSheet("font-size: 16px; color: #666; text-align: center; margin: 50px;")
            welcome_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(welcome_label)
        else:
            # 根据文件类型显示不同内容
            if file_type == "csv" or file_type == "jzrj":
                # 创建表格显示文件内容
                file_table = QTableWidget()
                file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                layout.addWidget(file_table)
                
                # 这里可以添加加载文件内容的逻辑
        
        # 添加标签页
        tab_index = self.tab_widget.addTab(tab_content, title)
        self.tab_widget.setCurrentIndex(tab_index)
        
        return tab_index

    def close_tab(self, index):
        """关闭标签页"""
        if self.tab_widget.count() > 1:  # 确保至少保留一个标签页
            self.tab_widget.removeTab(index)
        else:
            # 如果只剩一个标签页，重置为欢迎页
            self.tab_widget.clear()
            self.add_new_tab("欢迎使用", "welcome")


# 主程序入口
if __name__ == "__main__":
    # 确保中文显示正常
    font = QFont("Source Han Sans CN", 10)
    
    app = QApplication(sys.argv)
    app.setFont(font)
    
    # 检查并创建资源目录
    if not os.path.exists("resources"):
        os.makedirs("resources")
    
    window = PennAicoinMainWindow()
    window.show()
    
    sys.exit(app.exec())
import os
import sys
import platform
import time
import sqlite3
import csv
import json
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asymmetric_padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView, QSizePolicy, QTextEdit, QListWidget, QListWidgetItem, QStackedWidget, QColorDialog, QCheckBox, QFileDialog, QSlider, QTabWidget,
    QInputDialog
)
from PyQt5.QtCore import QDate, Qt, QTimer, pyqtSignal, QThread, QSettings
from PyQt5.QtGui import QIcon, QPixmap, QKeySequence
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtWidgets import QGroupBox
import pyaudio
from PyQt5.QtWidgets import QKeySequenceEdit
import wave
import jieba
import vosk
import re


def resource_path(relative_path):
    """获取资源文件的绝对路径，适用于PyInstaller打包后的程序"""
    try:
        # PyInstaller创建的临时目录
        base_path = sys._MEIPASS
    except Exception:
        # 普通运行时的目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class VoiceRecognition(QThread):
    recognized_text = pyqtSignal(str)
    recording_stopped = pyqtSignal()

    def __init__(self, model_path="resources/vosk-model-small-cn-0.22", timeout=20):
        super().__init__()
        self.model_path = model_path
        self.is_recording = False
        self._stop_requested = False  # 添加停止请求标志
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
            while self.is_recording and not self._stop_requested:  # 检查停止请求标志
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
                # 检查是否需要停止
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
            self._stop_requested = True  # 设置停止请求标志
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.p:
                self.p.terminate()
            self.quit()  # 停止线程的事件循环
            self.wait()  # 等待线程完全停止
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

            # 读取哈希值
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


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setGeometry(100, 100, 600, 400)
        self.password_enabled = False
        self.file_manager = FileManager("accounting.jzrj")
        self.parent_app = parent  # 保存父窗口引用

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
                border-left: 3px solid #4CAF50;
                color: #4CAF50;
            }
        """)
        menu_items = ["主题", "用户协议", "文件管理", "文件加密", "快捷键", "关于"]
        for item in menu_items:
            self.menu_list.addItem(item)
        self.menu_list.setCurrentRow(7)  # 默认选中“关于”

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
        self.add_menu_page("主题", self.create_theme_settings_page())
        self.add_menu_page("用户协议", self.create_user_agreement_page())
        self.add_menu_page("文件管理", self.create_file_management_page())
        self.add_menu_page("文件加密", self.create_file_encryption_page())
        self.add_menu_page("快捷键", self.create_shortcuts_page())
        self.add_menu_page("关于", self.create_about_page())

    def add_menu_page(self, title, widget):
        """将页面添加到堆叠窗口"""
        self.stacked_widget.addWidget(widget)

    def create_theme_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        theme_group = QGroupBox("主题设置")
        theme_layout = QVBoxLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["默认主题", "清新蓝绿", "优雅紫金", "现代灰绿", "专业深色", "明亮活泼", "自定义"])
        self.theme_combo.currentIndexChanged.connect(self.apply_theme)
        theme_layout.addWidget(self.theme_combo)

        custom_theme_group = QGroupBox("自定义主题")
        custom_theme_layout = QVBoxLayout()

        color_button_layout = QHBoxLayout()
        self.background_color_btn = QPushButton("背景颜色")
        self.background_color_btn.clicked.connect(lambda: self.show_color_dialog(self.background_color_btn))
        color_button_layout.addWidget(self.background_color_btn)

        self.button_color_btn = QPushButton("按钮颜色")
        self.button_color_btn.clicked.connect(lambda: self.show_color_dialog(self.button_color_btn))
        color_button_layout.addWidget(self.button_color_btn)

        self.title_color_btn = QPushButton("标题颜色")
        self.title_color_btn.clicked.connect(lambda: self.show_color_dialog(self.title_color_btn))
        color_button_layout.addWidget(self.title_color_btn)

        self.selected_color_btn = QPushButton("选中颜色")
        self.selected_color_btn.clicked.connect(lambda: self.show_color_dialog(self.selected_color_btn))
        color_button_layout.addWidget(self.selected_color_btn)

        custom_theme_layout.addLayout(color_button_layout)
        theme_layout.addWidget(custom_theme_group)

        # 预留背景图片和透明度设置
        background_image_layout = QHBoxLayout()
        self.background_image_btn = QPushButton("背景图片")
        self.background_image_btn.clicked.connect(self.set_background_image)
        background_image_layout.addWidget(self.background_image_btn)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.set_opacity)
        background_image_layout.addWidget(self.opacity_slider)

        theme_layout.addLayout(background_image_layout)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        layout.addStretch()
        return page

    def create_user_agreement_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # 用户协议内容
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

    def create_shortcuts_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # 快捷键设置内容
        shortcuts_label = QLabel("快捷键设置内容")
        layout.addWidget(shortcuts_label)

        # 示例：添加快捷键设置
        self.add_shortcut_edit = QKeySequenceEdit()
        self.add_shortcut_edit.setKeySequence(QKeySequence("Ctrl+A"))
        layout.addWidget(QLabel("添加记录:"))
        layout.addWidget(self.add_shortcut_edit)

        self.delete_shortcut_edit = QKeySequenceEdit()
        self.delete_shortcut_edit.setKeySequence(QKeySequence("Ctrl+D"))
        layout.addWidget(QLabel("删除记录:"))
        layout.addWidget(self.delete_shortcut_edit)

        self.modify_shortcut_edit = QKeySequenceEdit()
        self.modify_shortcut_edit.setKeySequence(QKeySequence("Ctrl+M"))
        layout.addWidget(QLabel("修改记录:"))
        layout.addWidget(self.modify_shortcut_edit)

        self.export_shortcut_edit = QKeySequenceEdit()
        self.export_shortcut_edit.setKeySequence(QKeySequence("Ctrl+E"))
        layout.addWidget(QLabel("导出数据:"))
        layout.addWidget(self.export_shortcut_edit)

        self.import_shortcut_edit = QKeySequenceEdit()
        self.import_shortcut_edit.setKeySequence(QKeySequence("Ctrl+I"))
        layout.addWidget(QLabel("导入数据:"))
        layout.addWidget(self.import_shortcut_edit)

        self.settings_shortcut_edit = QKeySequenceEdit()
        self.settings_shortcut_edit.setKeySequence(QKeySequence("Ctrl+S"))
        layout.addWidget(QLabel("打开设置:"))
        layout.addWidget(self.settings_shortcut_edit)

        self.about_shortcut_edit = QKeySequenceEdit()
        self.about_shortcut_edit.setKeySequence(QKeySequence("Ctrl+H"))
        layout.addWidget(QLabel("关于信息:"))
        layout.addWidget(self.about_shortcut_edit)

        self.voice_shortcut_edit = QKeySequenceEdit()
        self.voice_shortcut_edit.setKeySequence(QKeySequence("Ctrl+V"))
        layout.addWidget(QLabel("语音识别:"))
        layout.addWidget(self.voice_shortcut_edit)

        layout.addStretch()
        return page

    def create_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        version_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap(resource_path('resources/robot_icon.png'))  # 使用动态解析路径
        icon_label.setPixmap(pixmap.scaled(64, 64, Qt.IgnoreAspectRatio))
        version_layout.addWidget(icon_label)
        version_label = QLabel("使用条款、版权声明与开源协议")
        version_label.setStyleSheet("font-size: 18px; color: #333;")
        version_layout.addWidget(version_label)
        version_layout.addStretch()
        layout.addLayout(version_layout)

        # 加载 MIT License (简体中文)
        self.mit_license_zh_cn_label = QTextEdit()
        self.mit_license_zh_cn_label.setReadOnly(True)
        self.mit_license_zh_cn_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        self.load_text_file(resource_path(os.path.join("license", "MIT_License_ZH-CN.txt")), self.mit_license_zh_cn_label)
        layout.addWidget(self.mit_license_zh_cn_label)

        # 加载 MIT License (繁体中文)
        self.mit_license_zh_tw_label = QTextEdit()
        self.mit_license_zh_tw_label.setReadOnly(True)
        self.mit_license_zh_tw_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        self.load_text_file(resource_path(os.path.join("license", "MIT_License_ZH-TW.txt")), self.mit_license_zh_tw_label)
        layout.addWidget(self.mit_license_zh_tw_label)

        # 加载 MIT License (英文)
        self.mit_license_en_label = QTextEdit()
        self.mit_license_en_label.setReadOnly(True)
        self.mit_license_en_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        self.load_text_file(resource_path(os.path.join("license", "MIT_License_EN.txt")), self.mit_license_en_label)
        layout.addWidget(self.mit_license_en_label)

        # 加载 LEGAL.md
        self.legal_md_label = QTextEdit()
        self.legal_md_label.setReadOnly(True)
        self.legal_md_label.setStyleSheet("background-color: transparent; border: none; font-size: 12px; color: #666;")
        self.load_text_file(resource_path(os.path.join("license", "LEGAL.md.txt")), self.legal_md_label)
        layout.addWidget(self.legal_md_label)

        layout.addStretch()
        return page

    def load_text_file(self, file_path, text_edit):
        """加载文本文件内容到指定的 QTextEdit 控件中"""
        try:
            # 使用 resource_path 处理路径
            full_path = resource_path(file_path)
            with open(full_path, 'r', encoding='utf-8') as file:
                content = file.read()
                text_edit.setText(content)
        except Exception as e:
            text_edit.setText(f"无法加载文件：{file_path}\n错误信息：{str(e)}")
            print(f"无法加载文件：{file_path}\n错误信息：{str(e)}")

    def load_user_agreement(self):
        """加载用户协议文件内容到 QTextEdit 控件中"""
        try:
            file_path = resource_path(os.path.join("license", "user_agreement.txt"))
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                self.agreement_text.setText(content)
        except Exception as e:
            self.agreement_text.setText(f"无法加载用户协议文件：{file_path}\n错误信息：{str(e)}")

    def show_color_dialog(self, button):
        """显示颜色选择对话框"""
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")
            # 如果是背景颜色按钮，则应用到整个应用
            if button == self.background_color_btn:
                self.apply_custom_theme()

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
        self.parent_app.setStyleSheet("""
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
        self.parent_app.setStyleSheet("""
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
        self.parent_app.setStyleSheet("""
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
        self.parent_app.setStyleSheet("""
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
        self.parent_app.setStyleSheet("""
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
        self.parent_app.setStyleSheet("""
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

        self.parent_app.setStyleSheet(f"""
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

    def set_background_image(self):
        """设置背景图片"""
        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("选择背景图片")
        file_dialog.setLabelText(QFileDialog.Accept, "打开")
        file_dialog.setNameFilter("图片文件 (*.png *.jpg *.jpeg *.bmp)")
        file_dialog.setFileMode(QFileDialog.ExistingFile)

        if file_dialog.exec_():
            file_path = file_dialog.selectedFiles()[0]
            self.background_image_path = file_path
            self.apply_custom_theme()

    def set_opacity(self, value):
        """设置背景图片透明度"""
        self.opacity_value = value
        self.apply_custom_theme()

    def export_to_csv(self):
        """导出数据到 CSV 文件"""
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("导出到CSV文件")
            file_dialog.setLabelText(QFileDialog.Accept, "保存")
            file_dialog.setNameFilter("CSV文件 (*.csv)")
            file_dialog.setDefaultSuffix("csv")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)

            if file_dialog.exec_():
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

            if file_dialog.exec_():
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

            if file_dialog.exec_():
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

            if file_dialog.exec_():
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


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("用户登录")
        self.setGeometry(300, 300, 400, 200)

        layout = QVBoxLayout()

        # 用户名输入
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        self.username_input = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        layout.addLayout(username_layout)

        # 密码输入
        password_layout = QHBoxLayout()
        password_label = QLabel("密码:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # 登录按钮
        button_layout = QHBoxLayout()
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self.login)
        self.register_button = QPushButton("注册")
        self.register_button.clicked.connect(self.register)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "登录失败", "用户名和密码不能为空！")
            return

        # 这里应从数据库或配置文件中验证用户
        # 仅为示例，实际应用中应使用安全的存储方式
        users = [
            {"username": "admin", "password": "admin123", "permission": "Administrator"},
        ]

        for user in users:
            if user["username"] == username and user["password"] == password:
                QMessageBox.information(self, "登录成功", f"欢迎 {username}！")
                self.accept()
                return

        QMessageBox.warning(self, "登录失败", "用户名或密码错误！")

    def register(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "注册失败", "用户名和密码不能为空！")
            return

        # 这里应将用户注册信息保存到数据库或配置文件中
        # 仅为示例，实际应用中应使用安全的存储方式
        QMessageBox.information(self, "注册成功", f"用户 {username} 已成功注册！")
        self.accept()


class AccountingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_user = "admin"  # 默认登录为管理员
        self.init_ui()
        self.init_db()
        self.voice_thread = None
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.load_records)  # 每分钟刷新一次
        self.update_timer.start(60000)  # 60000毫秒 = 1分钟
        self.password_enabled = False
        self.shortcuts = {}
        self.init_shortcuts()
        self.check_password_on_start()
        self.load_records()  # 程序启动时立即加载记录

    def init_ui(self):
        self.setWindowTitle('记账本程序')
        self.setGeometry(100, 100, 1200, 800)

        self.setWindowIcon(QIcon(resource_path('resources/user_icon.png')))  # 设置图标

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

        self.side_bar = QVBoxLayout()
        self.side_bar.setAlignment(Qt.AlignTop)
        self.side_bar.setSpacing(5)

        user_info_layout = QHBoxLayout()
        user_avatar_label = QLabel()
        user_avatar_label.setPixmap(QPixmap(resource_path('resources/user_icon.png')).scaled(40, 40, Qt.IgnoreAspectRatio))
        user_info_layout.addWidget(user_avatar_label)
        self.user_label = QLabel("管理员")
        user_info_layout.addWidget(self.user_label)
        user_info_layout.addStretch()
        self.side_bar.addLayout(user_info_layout)

        button_layout = QVBoxLayout()

        self.add_button = QPushButton('Add-添加')
        self.add_button.setIcon(QIcon(resource_path('resources/Add_icon.png')))
        self.add_button.setFixedHeight(35)
        self.add_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_button.clicked.connect(self.show_add_dialog)
        button_layout.addWidget(self.add_button)

        self.delete_button = QPushButton('Delete-删除')
        self.delete_button.setIcon(QIcon(resource_path('resources/delete_icon.png')))
        self.delete_button.setFixedHeight(35)
        self.delete_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_record)
        button_layout.addWidget(self.delete_button)

        self.modify_button = QPushButton('Write-修改')
        self.modify_button.setIcon(QIcon(resource_path('resources/Write_icon.png')))
        self.modify_button.setFixedHeight(35)
        self.modify_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.modify_button.clicked.connect(self.modify_record)
        button_layout.addWidget(self.modify_button)

        self.export_button = QPushButton('Export-导出')
        self.export_button.setIcon(QIcon(resource_path('resources/Export_icon.png')))
        self.export_button.setFixedHeight(35)
        self.export_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.export_button.clicked.connect(self.show_export_prompt)
        button_layout.addWidget(self.export_button)

        self.import_button = QPushButton('Import-导入')
        self.import_button.setIcon(QIcon(resource_path('resources/Import_icon.png')))
        self.import_button.setFixedHeight(35)
        self.import_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_button.clicked.connect(self.show_import_prompt)
        button_layout.addWidget(self.import_button)

        self.settings_button = QPushButton('Settings-设置')
        self.settings_button.setIcon(QIcon(resource_path('resources/settings_icon.png')))
        self.settings_button.setFixedHeight(35)
        self.settings_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        button_layout.addWidget(self.settings_button)

        self.about_button = QPushButton('About-关于')
        self.about_button.setIcon(QIcon(resource_path('resources/about_icon.png')))
        self.about_button.setFixedHeight(35)
        self.about_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.about_button.clicked.connect(self.show_about_info)
        button_layout.addWidget(self.about_button)

        self.voice_button = QPushButton('🎤 开始录音')
        self.voice_button.setFixedHeight(35)
        self.voice_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_button.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.voice_button)

        # 搜索按钮和语音识别显示
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索记录...")
        self.search_input.setFixedHeight(30)
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedHeight(30)
        self.search_button.clicked.connect(self.search_records)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        button_layout.addLayout(search_layout)

        self.recognition_display = QTextEdit()
        self.recognition_display.setReadOnly(True)
        self.recognition_display.setMaximumHeight(100)
        button_layout.addWidget(self.recognition_display)

        self.side_bar.addLayout(button_layout)

        robot_layout = QHBoxLayout()
        robot_label = QLabel()
        robot_label.setPixmap(QPixmap(resource_path('resources/robot_icon.png')).scaled(200, 125, Qt.IgnoreAspectRatio))
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

        self.tab_widget = QTabWidget()

        self.all_records_tab = QWidget()
        self.income_tab = QWidget()
        self.expense_tab = QWidget()
        self.stats_tab = QWidget()

        self.tab_widget.addTab(self.all_records_tab, "所有记录")
        self.tab_widget.addTab(self.income_tab, "收入记录")
        self.tab_widget.addTab(self.expense_tab, "支出记录")

        side_and_table_layout.addWidget(self.tab_widget, 1)
        self.main_layout.addLayout(side_and_table_layout)

        # 设置标签页内容
        self.setup_all_records_tab()
        self.setup_income_tab()
        self.setup_expense_tab()
        self.setup_stats_tab()

        self.update_bottom_info()
        self.update_time()

    def setup_all_records_tab(self):
        layout = QVBoxLayout(self.all_records_tab)
        self.all_records_table = QTableWidget()
        self.all_records_table.setColumnCount(6)
        self.all_records_table.setHorizontalHeaderLabels(["日期", "金额", "币种", "收支类型", "详细分类", "备注信息"])
        self.all_records_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.all_records_table)

    def setup_income_tab(self):
        layout = QVBoxLayout(self.income_tab)
        self.income_table = QTableWidget()
        self.income_table.setColumnCount(6)
        self.income_table.setHorizontalHeaderLabels(["日期", "金额", "币种", "类型", "分类", "备注"])
        self.income_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.income_table)

    def setup_expense_tab(self):
        layout = QVBoxLayout(self.expense_tab)
        self.expense_table = QTableWidget()
        self.expense_table.setColumnCount(6)
        self.expense_table.setHorizontalHeaderLabels(["日期", "金额", "币种", "类型", "分类", "备注"])
        self.expense_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.expense_table)

    def setup_stats_tab(self):
        layout = QVBoxLayout(self.stats_tab)
        self.stats_label = QLabel("统计分析内容")
        layout.addWidget(self.stats_label)

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

        # 更新所有记录标签页
        self.all_records_table.setRowCount(len(records))
        for row, record in enumerate(records):
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])
            self.all_records_table.setItem(row, 0, date_item)
            self.all_records_table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.all_records_table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.all_records_table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.all_records_table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.all_records_table.setItem(row, 5, QTableWidgetItem(record[6]))

        # 更新收入记录标签页
        self.cursor.execute("SELECT * FROM records WHERE type='收入'")
        income_records = self.cursor.fetchall()
        self.income_table.setRowCount(len(income_records))
        for row, record in enumerate(income_records):
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])
            self.income_table.setItem(row, 0, date_item)
            self.income_table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.income_table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.income_table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.income_table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.income_table.setItem(row, 5, QTableWidgetItem(record[6]))

        # 更新支出记录标签页
        self.cursor.execute("SELECT * FROM records WHERE type='支出'")
        expense_records = self.cursor.fetchall()
        self.expense_table.setRowCount(len(expense_records))
        for row, record in enumerate(expense_records):
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])
            self.expense_table.setItem(row, 0, date_item)
            self.expense_table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.expense_table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.expense_table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.expense_table.setItem(row, 4, QTableWidgetItem(record[5]))
            self.expense_table.setItem(row, 5, QTableWidgetItem(record[6]))

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
            model_path = resource_path("resources/vosk-model-small-cn-0.22")
            timeout = 20
            self.voice_thread = VoiceRecognition(model_path, timeout)
            self.voice_thread.recognized_text.connect(self.process_voice_input)
            self.voice_thread.recording_stopped.connect(self.handle_recording_stopped)
            self.voice_thread.start()
            QMessageBox.information(None, "开始录音", "录音已开始...（如果想手动停止录音，请等待加载完成后再试！！！")
        except Exception as e:
            print("开始录音时出错:", e)

    def stop_recording(self):
        try:
            self.voice_button.setText('🎤 开始录音')
            if self.voice_thread and self.voice_thread.isRunning():
                self.voice_thread.is_recording = False
                self.voice_thread.quit()
                self.voice_thread.wait()  # 确保线程完全停止
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
        selected_row = self.all_records_table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return

        item = self.all_records_table.item(selected_row, 0)
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
        selected_row = self.all_records_table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return

        item = self.all_records_table.item(selected_row, 0)
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
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("导出账本数据")
            file_dialog.setLabelText(QFileDialog.Accept, "保存")
            file_dialog.setNameFilter("CSV文件 (*.csv)")
            file_dialog.setDefaultSuffix("csv")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)

            if file_dialog.exec_():
                file_path = file_dialog.selectedFiles()[0]
                file_manager = FileManager("accounting.jzrj")
                if file_manager.export_to_csv("accounting.db", file_path):
                    QMessageBox.information(self, "导出成功", f"账本数据已成功导出为CSV文件：\n{file_path}")
                else:
                    QMessageBox.warning(self, "导出失败", "导出账本数据时发生错误！")
        except Exception as e:
            print(f"显示导出提示时出错:", e)

    def show_import_prompt(self):
        try:
            file_dialog = QFileDialog()
            file_dialog.setWindowTitle("导入账本数据")
            file_dialog.setLabelText(QFileDialog.Accept, "打开")
            file_dialog.setNameFilter("CSV文件 (*.csv)")
            file_dialog.setFileMode(QFileDialog.ExistingFile)

            if file_dialog.exec_():
                file_path = file_dialog.selectedFiles()[0]
                file_manager = FileManager("accounting.jzrj")
                if file_manager.import_from_csv("accounting.db", file_path):
                    QMessageBox.information(self, "导入成功", f"账本数据已成功从CSV文件导入：\n{file_path}")
                    self.load_records()
                else:
                    QMessageBox.warning(self, "导入失败", "导入账本数据时发生错误！")
        except Exception as e:
            print(f"显示导入提示时出错:", e)

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
            f"当前用户: {self.current_user if self.current_user else '未登录'}\n"
            f"软件版本: Version.0.0.1系列"
        )

    def show_settings_dialog(self):
        """显示设置对话框"""
        try:
            settings_dialog = SettingsDialog(self)
            settings_dialog.exec_()
        except Exception as e:
            print(f"显示设置对话框时出错: {e}")
            QMessageBox.critical(self, "错误", f"显示设置对话框时出错: {str(e)}")

    def check_password_on_start(self):
        """检查是否需要密码验证"""
        if not self.current_user:
            self.show_login_dialog()

    def show_login_dialog(self):
        """显示登录对话框"""
        login_dialog = LoginDialog(self)
        if login_dialog.exec_() == QDialog.Accepted:
            self.current_user = "admin" 
            self.user_label.setText(f"当前用户: {self.current_user}")
            self.update_bottom_info()

    def init_shortcuts(self):
        """初始化快捷键"""
        # 默认快捷键
        self.shortcuts = {
            "add": QKeySequence("Ctrl+A"),
            "delete": QKeySequence("Ctrl+D"),
            "modify": QKeySequence("Ctrl+M"),
            "export": QKeySequence("Ctrl+E"),
            "import": QKeySequence("Ctrl+I"),
            "settings": QKeySequence("Ctrl+S"),
            "about": QKeySequence("Ctrl+H"),
            "voice": QKeySequence("Ctrl+V"),
            "search": QKeySequence("Ctrl+F")
        }

        # 设置快捷键
        QShortcut(self.shortcuts["add"], self).activated.connect(self.show_add_dialog)
        QShortcut(self.shortcuts["delete"], self).activated.connect(self.delete_record)
        QShortcut(self.shortcuts["modify"], self).activated.connect(self.modify_record)
        QShortcut(self.shortcuts["export"], self).activated.connect(self.show_export_prompt)
        QShortcut(self.shortcuts["import"], self).activated.connect(self.show_import_prompt)
        QShortcut(self.shortcuts["settings"], self).activated.connect(self.show_settings_dialog)
        QShortcut(self.shortcuts["about"], self).activated.connect(self.show_about_info)
        QShortcut(self.shortcuts["voice"], self).activated.connect(self.toggle_recording)
        QShortcut(self.shortcuts["search"], self).activated.connect(lambda: self.search_input.setFocus())

    def search_records(self):
        search_text = self.search_input.text().lower()
        if not search_text:
            self.load_records()  # 如果搜索框为空，显示所有记录
            return

        # 筛选符合条件的记录
        filtered_records = []
        for row in range(self.all_records_table.rowCount()):
            date_item = self.all_records_table.item(row, 0)
            amount_item = self.all_records_table.item(row, 1)
            category_item = self.all_records_table.item(row, 4)
            note_item = self.all_records_table.item(row, 5)

            if (search_text in date_item.text().lower() or
                search_text in amount_item.text().lower() or
                search_text in category_item.text().lower() or
                search_text in note_item.text().lower()):
                filtered_records.append(row)

        # 更新表格显示
        self.all_records_table.clearContents()
        self.all_records_table.setRowCount(len(filtered_records))
        for idx, row in enumerate(filtered_records):
            for col in range(self.all_records_table.columnCount()):
                self.all_records_table.setItem(idx, col, QTableWidgetItem(self.all_records_table.item(row, col).text()))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AccountingApp()
    ex.show()
    sys.exit(app.exec_())

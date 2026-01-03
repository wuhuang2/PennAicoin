import sys
import os
import time
import csv
import llama_cpp  
from docx import Document  
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                              QPushButton, QTextEdit, QFileDialog, QLabel, QProgressBar, 
                              QMessageBox, QSplitter, QLineEdit)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QFont, QTextCursor, QColor

class WorkerSignals(QObject):
    progress_updated = Signal(int)
    status_updated = Signal(str)
    result_ready = Signal(str)
    model_loaded = Signal(bool)

class ModelLoader(QThread):
    def __init__(self, model_path):
        super().__init__()
        self.model_path = model_path
        self.signals = WorkerSignals()
        self.model = None
    def run(self):
        try:
            self.signals.status_updated.emit("正在加载模型...")
            self.signals.progress_updated.emit(10)
            self.model = llama_cpp.Llama(model_path=self.model_path, n_ctx=4096, n_threads=4, n_gpu_layers=0)
            self.signals.progress_updated.emit(100)
            self.signals.status_updated.emit("模型加载完成")
            self.signals.model_loaded.emit(True)
        except Exception as e:
            self.signals.status_updated.emit(f"模型加载失败: {str(e)}")
            self.signals.progress_updated.emit(0)
            self.signals.model_loaded.emit(False)

class InferenceWorker(QThread):
    def __init__(self, model, prompt):
        super().__init__()
        self.model = model
        self.prompt = prompt
        self.signals = WorkerSignals()
        self.stop_flag = False
    def run(self):
        try:
            self.signals.status_updated.emit("正在生成回答...")
            self.signals.progress_updated.emit(0)
            progress = 0
            full_response = ""  # 缓存完整输出用于分割思考过程
            for token in self.model.create_completion(
                self.prompt, stream=True, max_tokens=1024, 
                temperature=0.7, stop=["\nUser:", "\nAssistant:"]
            ):
                if self.stop_flag:
                    self.signals.status_updated.emit("生成已取消")
                    return
                token_text = token["choices"][0]["text"].replace("\n", " ").replace("  ", " ")
                full_response += token_text
                self.signals.result_ready.emit(token_text)  # 流式发送当前token
                progress += 1
                if progress > 100: progress = 100
                self.signals.progress_updated.emit(progress)
                time.sleep(0.005)
            self.signals.progress_updated.emit(100)
            self.signals.status_updated.emit("回答生成完成")
        except Exception as e:
            self.signals.status_updated.emit(f"生成失败: {str(e)}")
            self.signals.progress_updated.emit(0)
    def stop(self):
        self.stop_flag = True

class FileProcessor(QThread):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.signals = WorkerSignals()
    def run(self):
        try:
            self.signals.status_updated.emit("正在处理文件...")
            self.signals.progress_updated.emit(20)
            text = self.extract_text_from_file(self.file_path)
            self.signals.progress_updated.emit(100)
            self.signals.status_updated.emit("文件处理完成")
            self.signals.result_ready.emit(text)
        except Exception as e:
            self.signals.status_updated.emit(f"文件处理失败: {str(e)}")
            self.signals.progress_updated.emit(0)
    def extract_text_from_file(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return '\n'.join([f"行 {i+1}: {', '.join(row)}" for i, row in enumerate(csv.reader(f))])
        elif ext == '.docx':
            return '\n'.join([para.text for para in Document(file_path).paragraphs])
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            raise Exception(f"不支持的文件类型: {ext}，当前支持: .csv, .docx, .txt")

class AIChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = None
        self.inference_worker = None
        self.ai_prefix_added = False  # 控制AI前缀只添加一次
        self.full_response = ""  # 缓存完整响应用于分割
        self.thoughts_finished = False  # 标记思考过程是否结束
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("AI大模型驱动程序（思考/输出分隔版）")
        self.setGeometry(100, 100, 1000, 800)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部控制区
        control_layout = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setPlaceholderText("模型文件路径")
        self.model_path_edit.setReadOnly(True)
        self.select_model_btn = QPushButton("选择模型(GGUF)")
        self.select_model_btn.clicked.connect(self.select_model)
        self.load_model_btn = QPushButton("加载模型")
        self.load_model_btn.clicked.connect(self.load_model)
        self.load_model_btn.setEnabled(False)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("文件路径")
        self.file_path_edit.setReadOnly(True)
        self.upload_file_btn = QPushButton("上传文件")
        self.upload_file_btn.clicked.connect(self.upload_file)
        control_layout.addWidget(self.model_path_edit)
        control_layout.addWidget(self.select_model_btn)
        control_layout.addWidget(self.load_model_btn)
        control_layout.addWidget(self.file_path_edit)
        control_layout.addWidget(self.upload_file_btn)
        
        # 聊天区域
        splitter = QSplitter(Qt.Vertical)
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setFont(QFont("SimHei", 10))
        splitter.addWidget(self.chat_history)
        
        # 输入区域
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        self.user_input = QTextEdit()
        self.user_input.setPlaceholderText("请输入您的问题...")
        self.user_input.setFont(QFont("SimHei", 10))
        self.user_input.setMinimumHeight(100)
        btn_layout = QHBoxLayout()
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setEnabled(False)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_chat)
        self.cancel_btn = QPushButton("取消生成")
        self.cancel_btn.clicked.connect(self.cancel_inference)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.send_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.cancel_btn)
        input_layout.addWidget(self.user_input)
        input_layout.addLayout(btn_layout)
        splitter.addWidget(input_widget)
        splitter.setSizes([500, 200])
        
        # 进度条和状态
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(control_layout)
        main_layout.addWidget(splitter)
        main_layout.addLayout(status_layout)
    
    def select_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择GGUF模型文件", "", "GGUF模型文件 (*.gguf)")
        if file_path:
            self.model_path_edit.setText(file_path)
            self.load_model_btn.setEnabled(True)
    
    def load_model(self):
        model_path = self.model_path_edit.text()
        if not model_path or not os.path.exists(model_path):
            QMessageBox.warning(self, "警告", "请选择有效的模型文件")
            return
        self.select_model_btn.setEnabled(False)
        self.load_model_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.model_loader = ModelLoader(model_path)
        self.model_loader.signals.progress_updated.connect(self.update_progress)
        self.model_loader.signals.status_updated.connect(self.update_status)
        self.model_loader.signals.model_loaded.connect(self.on_model_loaded)
        self.model_loader.start()
    
    def on_model_loaded(self, success):
        if success:
            self.model = self.model_loader.model
            QMessageBox.information(self, "成功", "模型加载成功")
            self.send_btn.setEnabled(True)
        else:
            QMessageBox.critical(self, "失败", "模型加载失败")
        self.select_model_btn.setEnabled(True)
        self.load_model_btn.setEnabled(True)
    
    def upload_file(self):
        if not self.model:
            QMessageBox.warning(self, "警告", "请先加载模型")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "支持的文件 (*.csv *.docx *.txt)")
        if not file_path:
            return
        self.file_path_edit.setText(file_path)
        self.upload_file_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.file_processor = FileProcessor(file_path)
        self.file_processor.signals.progress_updated.connect(self.update_progress)
        self.file_processor.signals.status_updated.connect(self.update_status)
        self.file_processor.signals.result_ready.connect(self.on_file_processed)
        self.file_processor.start()
    
    def on_file_processed(self, file_content):
        self.upload_file_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        file_name = os.path.basename(self.file_path_edit.text())
        self.chat_history.append(f"📎 已加载文件: {file_name}\n")
        if len(file_content) > 1000:
            display_content = file_content[:1000] + "..."
            self.chat_history.append(f"文件内容预览:\n{display_content}\n")
        else:
            self.chat_history.append(f"文件内容:\n{file_content}\n")
        self.user_input.setPlainText("请分析一下这个文件，告诉我其中的关键信息（用中文回答）。")
    
    def send_message(self):
        user_message = self.user_input.toPlainText().strip()
        if not user_message:
            return
        if not self.model:
            QMessageBox.warning(self, "警告", "请先加载模型")
            return
        # 显示用户消息
        self.chat_history.append(f"👤 你:\n{user_message}\n")
        self.user_input.clear()
        # 重置状态变量
        self.ai_prefix_added = False
        self.full_response = ""
        self.thoughts_finished = False
        # 禁用按钮
        self.send_btn.setEnabled(False)
        self.upload_file_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        # 构建提示词（要求用`</think>`分隔思考和输出）
        history_text = self.chat_history.toPlainText().replace("👤 你:", "User:").replace("🤖 AI:", "Assistant:")
        prompt = f"{history_text}User: 请用中文回答，先输出思考过程，再用`</think>`分隔，最后输出最终回答（单行）：{user_message}Assistant:"
        # 启动推理线程
        self.inference_worker = InferenceWorker(self.model, prompt)
        self.inference_worker.signals.progress_updated.connect(self.update_progress)
        self.inference_worker.signals.status_updated.connect(self.update_status)
        self.inference_worker.signals.result_ready.connect(self.append_model_response)
        self.inference_worker.finished.connect(self.on_inference_finished)
        self.inference_worker.start()
    
    def append_model_response(self, text):
        self.full_response += text  # 缓存完整响应
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # 首次添加AI前缀
        if not self.ai_prefix_added:
            self.chat_history.insertPlainText("🤖 AI: ")
            self.ai_prefix_added = True
        
        # 检测分隔符`</think>`，区分思考过程和实际输出
        if "</think>" in self.full_response and not self.thoughts_finished:
            # 分割思考部分和输出部分
            thoughts_part, output_part = self.full_response.split("</think>", 1)
            # 清除当前已显示的内容（避免重复）
            self.chat_history.selectAll()
            self.chat_history.insertPlainText("")
            # 重新添加AI前缀
            self.chat_history.insertPlainText("🤖 AI: ")
            # 显示思考过程（灰色斜体）
            cursor = self.chat_history.textCursor()
            self.chat_history.setTextColor(QColor(100, 100, 100))  # 灰色
            self.chat_history.setFontItalic(True)
            self.chat_history.insertPlainText(thoughts_part)
            # 添加分割线
            self.chat_history.setFontItalic(False)
            self.chat_history.setTextColor(QColor(0, 0, 0))  # 黑色
            self.chat_history.insertPlainText("\n=== 思考结束 ===\n")
            # 显示实际输出
            self.chat_history.insertPlainText(output_part)
            # 更新状态
            self.thoughts_finished = True
            self.full_response = output_part  # 缓存输出部分
        else:
            # 未检测到分隔符时，按类型显示
            if self.thoughts_finished:
                # 输出部分（正常格式）
                self.chat_history.insertPlainText(text)
            else:
                # 思考部分（灰色斜体）
                self.chat_history.setTextColor(QColor(100, 100, 100))
                self.chat_history.setFontItalic(True)
                self.chat_history.insertPlainText(text)
                self.chat_history.setTextColor(QColor(0, 0, 0))
                self.chat_history.setFontItalic(False)
        
        self.chat_history.moveCursor(QTextCursor.End)
    
    def on_inference_finished(self):
        # 如果模型未输出分隔符，强制添加分割线
        if not self.thoughts_finished:
            self.chat_history.append("\n=== 无明显思考过程 ===")
        self.chat_history.append("\n")
        self.send_btn.setEnabled(True)
        self.upload_file_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.inference_worker = None
    
    def cancel_inference(self):
        if self.inference_worker and self.inference_worker.isRunning():
            self.inference_worker.stop()
            self.cancel_btn.setEnabled(False)
            self.ai_prefix_added = False
            self.thoughts_finished = False
    
    def clear_chat(self):
        self.chat_history.clear()
        self.file_path_edit.clear()
        self.ai_prefix_added = False
        self.thoughts_finished = False
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        self.status_label.setText(message)

if __name__ == "__main__":
    os.environ["QT_FONT_DPI"] = "96"
    app = QApplication(sys.argv)
    window = AIChatWindow()
    window.show()
    sys.exit(app.exec())
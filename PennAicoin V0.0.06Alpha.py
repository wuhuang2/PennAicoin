import sys
import platform
import time
import sqlite3
import getpass  # 用于获取当前用户名
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView, QSizePolicy, QTextEdit
)
from PyQt5.QtCore import QDate, Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap


class AccountingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_db()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_time)
        self.update_timer.start(1000)  # 每秒更新一次时间

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle('记账本程序')
        self.setGeometry(100, 100, 1200, 800)

        # 设置样式表，调整文字行距
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
            }
            QLabel {
                line-height: 1.5;  /* 增加文字行距 */
            }
            /* 其他样式保持不变 */
            QPushButton {
                border: 2px solid #8f8f91;
                border-radius: 6px;
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                  stop: 0 #f6f7fa, stop: 1 #dadbde);
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 14px;
                text-align: left;  /* 图标和文字左对齐 */
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

        # 顶部时间栏
        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignCenter)
        font = self.time_label.font()
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setMinimumHeight(30)

        # 左侧工具栏
        self.tool_bar = QToolBar(self)
        self.addToolBar(self.tool_bar)

        # 获取本地用户名
        self.current_user = getpass.getuser()

        # 初始化侧边栏布局
        self.side_bar = QVBoxLayout()
        self.side_bar.setAlignment(Qt.AlignTop)  # 使按钮靠上对齐
        self.side_bar.setSpacing(5)  # 减少按钮之间的间隔

        # 用户信息区域
        user_info_layout = QHBoxLayout()
        user_avatar_label = QLabel()
        user_avatar_label.setPixmap(QPixmap('user_icon.png').scaled(40, 40, Qt.IgnoreAspectRatio))  # 默认用户头像
        user_info_layout.addWidget(user_avatar_label)
        user_label = QLabel(f"本地用户: {self.current_user}")
        user_info_layout.addWidget(user_label)
        user_info_layout.addStretch()  # 添加伸缩空间，使用户信息左对齐
        self.side_bar.addLayout(user_info_layout)

        # 按钮布局
        button_layout = QVBoxLayout()

        # 添加按钮
        self.add_button = QPushButton('Add-添加')
        self.add_button.setIcon(QIcon('add_icon.png'))  # 设置添加按钮的图标
        self.add_button.setFixedHeight(35)  # 减少按钮高度
        self.add_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_button.clicked.connect(self.show_add_dialog)
        button_layout.addWidget(self.add_button)

        # 删除按钮
        self.delete_button = QPushButton('Delete-删除')
        self.delete_button.setIcon(QIcon('delete_icon.png'))  # 设置删除按钮的图标
        self.delete_button.setFixedHeight(35)  # 减少按钮高度
        self.delete_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_record)
        button_layout.addWidget(self.delete_button)

        # 修改按钮
        self.modify_button = QPushButton('Write-修改')
        self.modify_button.setIcon(QIcon('Write_icon.png'))  # 设置修改按钮的图标
        self.modify_button.setFixedHeight(35)  # 减少按钮高度
        self.modify_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.modify_button.clicked.connect(self.modify_record)
        button_layout.addWidget(self.modify_button)

        # 导出按钮
        self.export_button = QPushButton('Export-导出')
        self.export_button.setIcon(QIcon('Export_icon.png'))  # 设置导出按钮的图标
        self.export_button.setFixedHeight(35)  # 减少按钮高度
        self.export_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.export_button.clicked.connect(self.show_export_prompt)
        button_layout.addWidget(self.export_button)

        # 导入按钮
        self.import_button = QPushButton('Import-导入')
        self.import_button.setIcon(QIcon('Import_icon.png'))  # 设置导入按钮的图标
        self.import_button.setFixedHeight(35)  # 减少按钮高度
        self.import_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_button.clicked.connect(self.show_import_prompt)
        button_layout.addWidget(self.import_button)

        # 设置按钮
        self.settings_button = QPushButton('Settings-设置')
        self.settings_button.setIcon(QIcon('settings_icon.png'))  # 设置设置按钮的图标
        self.settings_button.setFixedHeight(35)  # 减少按钮高度
        self.settings_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_button.clicked.connect(self.show_settings_prompt)
        button_layout.addWidget(self.settings_button)

        # 关于按钮
        self.about_button = QPushButton('About-关于')
        self.about_button.setIcon(QIcon('about_icon.png'))  # 设置关于按钮的图标
        self.about_button.setFixedHeight(35)  # 减少按钮高度
        self.about_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.about_button.clicked.connect(self.show_about_info)
        button_layout.addWidget(self.about_button)

        self.side_bar.addLayout(button_layout)

        # Robot 标志
        robot_layout = QHBoxLayout()
        robot_label = QLabel()
        robot_label.setPixmap(QPixmap('robot_icon.png').scaled(200, 125, Qt.IgnoreAspectRatio))  # 减少图标大小
        robot_layout.addWidget(robot_label)
        self.side_bar.addLayout(robot_layout)

        # 底部信息
        bottom_info_layout = QHBoxLayout()
        self.bottom_info = QLabel()
        bottom_info_layout.addWidget(self.bottom_info)
        self.side_bar.addLayout(bottom_info_layout)

        # 中央窗口
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 主布局
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.addWidget(self.time_label)  # 添加时间标签到主布局

        # 侧边栏和表格布局
        side_and_table_layout = QHBoxLayout()
        self.side_bar_widget = QWidget()  # 创建一个 QWidget 作为侧边栏的容器
        self.side_bar_widget.setLayout(self.side_bar)
        self.side_bar_widget.setFixedWidth(200)  # 设置侧边栏的固定宽度为 200 像素
        side_and_table_layout.addWidget(self.side_bar_widget)  # 添加侧边栏容器

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["日期", "金额", "币种", "收支类型", "详细分类", "备注信息"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        side_and_table_layout.addWidget(self.table, 1)  # 添加表格并设置其伸缩因子为 1
        self.main_layout.addLayout(side_and_table_layout)

        # 版权声明
        copyright_layout = QHBoxLayout()
        copyright_label = QLabel("Copyright 2025 长治市屯留区第五中学机器人社团 饶晨曦 All Rights Reserved.\n 为参加第二十届宋庆龄少年儿童发明奖人工智能（编程）作品而开发。")
        copyright_layout.addWidget(copyright_label)
        copyright_layout.addStretch()  # 添加伸缩空间，使版权声明左对齐
        self.main_layout.addLayout(copyright_layout)

        # 更新底部信息
        self.update_bottom_info()

        # 初始化时间显示
        self.update_time()
    def init_db(self):
        """初始化数据库"""
        self.conn = sqlite3.connect('accounting.db')
        self.cursor = self.conn.cursor()  # 确保 self.cursor 是一个游标对象
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
            # 日期
            date_item = QTableWidgetItem(record[1])
            date_item.setData(Qt.UserRole, record[0])  # 存储 id
            self.table.setItem(row, 0, date_item)
            
            # 金额
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            
            # 币种
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            
            # 收支类型
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            
            # 详细分类
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))
            
            # 备注信息
            self.table.setItem(row, 5, QTableWidgetItem(record[6]))

    def show_add_dialog(self):
        """显示添加账本对话框"""
        try:
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
        except Exception as e:
            print(f"显示添加账本对话框时出错: {str(e)}")

    def add_new_record(self, date, amount_str, currency, type_, category, note, dialog):
        """添加新记录到数据库"""
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
        """删除选中的记录"""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return

        # 获取该行的 id
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
            self.load_records()  # 删除后重新加载数据

    def modify_record(self):
        """修改选中的记录"""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return

        # 获取该行的 id
        item = self.table.item(selected_row, 0)
        if item is None:
            QMessageBox.warning(self, "错误", "无法获取记录的 ID！")
            return
        record_id = item.data(Qt.UserRole)

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

    def update_record(self, record_id, date, amount_str, currency, type_, category, note, dialog):
        """更新记录到数据库"""
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
        """显示导出提示框"""
        QMessageBox.information(self, "导出功能", "导出功能暂未实现！")

    def show_import_prompt(self):
        """显示导入提示框"""
        QMessageBox.information(self, "导入功能", "导入功能暂未实现！")

    def show_settings_prompt(self):
        """显示设置提示框"""
        QMessageBox.information(self, "设置功能", "设置功能暂未实现！")

    def show_about_info(self):
        """显示关于信息"""
        QMessageBox.about(self, "关于", "记账本程序\n版本: 0.01\n开发者: 机器人团队")

    def update_time(self):
        """更新时间显示"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.time_label.setText(f"UTC+8 {current_time}")

    def update_bottom_info(self):
        """更新底部信息"""
        # 获取系统信息
        system = platform.system()
        release = platform.release()
        version = platform.version()
        architecture = platform.architecture()[0]

        # 更新底部标签文本
        self.bottom_info.setText(
            f"运行于: {system} {release} {architecture}\n"
            f"当前用户: {self.current_user}\n"
            f"软件版本: Version.0.01"
        )

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

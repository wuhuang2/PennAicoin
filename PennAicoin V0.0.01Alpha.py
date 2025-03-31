import sys
import sqlite3
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QMenuBar, QToolBar, QDialog, QHeaderView
)
from PyQt5.QtCore import QDate


class AccountingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_db()

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
        self.side_bar.addWidget(QLabel("侧边功能栏"))

        # 搜索记录按钮
        self.search_record_button = QPushButton('搜索记录')
        self.search_record_button.clicked.connect(self.show_search_dialog)
        self.side_bar.addWidget(self.search_record_button)

        # 添加账本按钮
        self.add_button = QPushButton('添加账本')
        self.add_button.clicked.connect(self.show_add_dialog)
        self.side_bar.addWidget(self.add_button)

        # 回收站按钮
        self.delete_button = QPushButton('回收站')
        self.delete_button.clicked.connect(self.delete_record)
        self.side_bar.addWidget(self.delete_button)

        # 语音输入按钮
        self.voice_button = QPushButton('语音输入')
        self.voice_button.clicked.connect(self.voice_input)
        self.side_bar.addWidget(self.voice_button)

        # 修改按钮
        self.modify_button = QPushButton('修改')
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

    def voice_input(self):
        """语音输入功能（预留）"""
        QMessageBox.information(self, "语音输入", "语音输入功能尚未实现。")

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
            /* 圆角按钮 */
            QPushButton {
                background-color: #3498db;
                color: #ffffff;
                border: none;
                border-radius: 10px; /* 设置圆角 */
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

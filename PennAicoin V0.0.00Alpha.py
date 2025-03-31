import sys
import sqlite3
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox
from PyQt5.QtCore import QDate


class AccountingApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.init_db()
        self.load_records()

    def initUI(self):
        # 输入布局
        input_layout = QVBoxLayout()

        # 日期输入
        date_layout = QHBoxLayout()
        self.date_label = QLabel("日期:")
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.date_label)
        date_layout.addWidget(self.date_input)
        input_layout.addLayout(date_layout)

        # 金额输入
        amount_layout = QHBoxLayout()
        self.amount_label = QLabel("金额:")
        self.amount_input = QLineEdit()
        amount_layout.addWidget(self.amount_label)
        amount_layout.addWidget(self.amount_input)
        input_layout.addLayout(amount_layout)

        # 收支类型输入
        type_layout = QHBoxLayout()
        self.type_label = QLabel("收支类型:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["收入", "支出"])
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_combobox)
        input_layout.addLayout(type_layout)

        # 详细分类输入
        category_layout = QHBoxLayout()
        self.category_label = QLabel("详细分类:")
        self.category_combobox = QComboBox()
        self.income_categories = ["工资收入", "奖金收入", "投资收益", "兼职收入"]
        self.expense_categories = ["餐饮", "购物", "交通", "住房", "娱乐", "医疗"]
        self.category_combobox.addItems(self.income_categories + self.expense_categories)
        category_layout.addWidget(self.category_label)
        category_layout.addWidget(self.category_combobox)
        input_layout.addLayout(category_layout)

        # 备注输入
        note_layout = QHBoxLayout()
        self.note_label = QLabel("备注信息:")
        self.note_input = QLineEdit()
        note_layout.addWidget(self.note_label)
        note_layout.addWidget(self.note_input)
        input_layout.addLayout(note_layout)

        # 按钮布局
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("添加记录")
        self.add_button.clicked.connect(self.add_record)
        self.modify_button = QPushButton("修改记录")
        self.modify_button.clicked.connect(self.modify_record)
        self.delete_button = QPushButton("删除记录")
        self.delete_button.clicked.connect(self.delete_record)
        self.query_button = QPushButton("查询记录")
        self.query_button.clicked.connect(self.query_records)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.modify_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.query_button)
        input_layout.addLayout(button_layout)

        # 表格显示记录
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["日期", "金额", "收支类型", "详细分类", "备注信息"])

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.addLayout(input_layout)
        main_layout.addWidget(self.table)

        self.setLayout(main_layout)
        self.setWindowTitle('记账本程序')
        self.setGeometry(300, 300, 800, 600)
        self.show()

    def init_db(self):
        self.conn = sqlite3.connect('accounting.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                amount REAL,
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
            self.table.setItem(row, 0, QTableWidgetItem(record[1]))
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))

    def add_record(self):
        date = self.date_input.date().toString("yyyy-MM-dd")
        try:
            amount = float(self.amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return
        type_ = self.type_combobox.currentText()
        category = self.category_combobox.currentText()
        note = self.note_input.text()

        self.cursor.execute("INSERT INTO records (date, amount, type, category, note) VALUES (?,?,?,?,?)",
                            (date, amount, type_, category, note))
        self.conn.commit()
        self.load_records()

    def modify_record(self):
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要修改的记录！")
            return
        record_id = selected_row + 1
        date = self.date_input.date().toString("yyyy-MM-dd")
        try:
            amount = float(self.amount_input.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的金额！")
            return
        type_ = self.type_combobox.currentText()
        category = self.category_combobox.currentText()
        note = self.note_input.text()

        self.cursor.execute("UPDATE records SET date=?, amount=?, type=?, category=?, note=? WHERE id=?",
                            (date, amount, type_, category, note, record_id))
        self.conn.commit()
        self.load_records()

    def delete_record(self):
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "错误", "请选择要删除的记录！")
            return
        record_id = selected_row + 1
        self.cursor.execute("DELETE FROM records WHERE id=?", (record_id,))
        self.conn.commit()
        self.load_records()

    def query_records(self):
        # 简单示例，按收支类型查询
        type_ = self.type_combobox.currentText()
        self.cursor.execute("SELECT * FROM records WHERE type=?", (type_,))
        records = self.cursor.fetchall()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(record[1]))
            self.table.setItem(row, 1, QTableWidgetItem(str(record[2])))
            self.table.setItem(row, 2, QTableWidgetItem(record[3]))
            self.table.setItem(row, 3, QTableWidgetItem(record[4]))
            self.table.setItem(row, 4, QTableWidgetItem(record[5]))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AccountingApp()
    sys.exit(app.exec_())

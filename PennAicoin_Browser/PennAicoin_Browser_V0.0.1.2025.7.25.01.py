import os
import markdown
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QToolBar, QAction, 
                             QPushButton, QLineEdit, QTabWidget, QStatusBar,
                             QFileDialog, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QFrame, QTextEdit, QScrollArea)
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtGui import QFont

class CustomWebEngineView(QWebEngineView):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        # 使用加载完成信号间接跟踪历史变化
        self.loadFinished.connect(self.on_load_finished)

    def createWindow(self, window_type):
        new_browser = CustomWebEngineView(self.main_window)
        self.main_window.add_new_tab(new_browser, "加载中...")
        return new_browser

    def on_load_finished(self, success):
        """页面加载完成后更新导航按钮状态"""
        if self.main_window:
            self.main_window.update_nav_buttons_state()

class PennaicoinBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.home_page_path = self.get_home_page_path()
        self.browser_version = "PennAicoin_Browser_V0.0.1.2025.7.25.01"
        self.init_ui()
        self.apply_styles()  # 应用QSS样式
        self.settings_tab = None  # 存储设置标签页引用

    def get_home_page_path(self):
        """获取html目录下的index.html作为默认主页"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        home_page_path = os.path.join(current_dir, "html", "index.html")
        return os.path.normpath(home_page_path)

    def init_ui(self):
        self.setWindowTitle("PennAicoin Browser")
        self.setGeometry(100, 100, 1200, 800)

        # 创建主布局容器
        self.main_container = QWidget()
        self.main_layout = QHBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 创建侧边导航栏（使用指定符号）
        self.create_sidebar()

        # 创建主内容区域
        self.create_main_content()

        self.setCentralWidget(self.main_container)
        self.setStatusBar(QStatusBar())

        self.enable_html5_features()
        self.load_start_page()

    def create_sidebar(self):
        """创建侧边导航栏，使用指定符号并加粗放大"""
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(60)  # 窄侧边栏宽度
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.sidebar_layout.setContentsMargins(5, 20, 5, 15)
        self.sidebar_layout.setSpacing(15)

        # 应用标识
        app_label = QLabel("P")
        app_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #3a7bd5;")
        app_label.setAlignment(Qt.AlignCenter)
        app_label.setFixedSize(40, 40)
        self.sidebar_layout.addWidget(app_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedWidth(40)
        line.setStyleSheet("background-color: #e1e4e8;")
        self.sidebar_layout.addWidget(line)

        # 主页按钮（使用⌂符号）
        self.home_btn = QPushButton("⌂")
        self.home_btn.setObjectName("navButton")
        self.home_btn.setToolTip("主页")
        self.home_btn.setFixedSize(40, 40)
        self.home_btn.clicked.connect(self.navigate_home)
        self.sidebar_layout.addWidget(self.home_btn)

        # 刷新按钮（使用↺符号）
        self.refresh_btn = QPushButton("↺")
        self.refresh_btn.setObjectName("navButton")
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.setFixedSize(40, 40)
        self.refresh_btn.clicked.connect(self.refresh_page)
        self.sidebar_layout.addWidget(self.refresh_btn)

        # 设置按钮（使用⚙符号）
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("navButton")
        self.settings_btn.setToolTip("设置")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.clicked.connect(self.show_settings)
        self.sidebar_layout.addWidget(self.settings_btn)

        # 占位符，将按钮推到顶部
        self.sidebar_layout.addStretch()
        
        # 将侧边栏添加到主布局
        self.main_layout.addWidget(self.sidebar)

    def create_main_content(self):
        """创建主内容区域"""
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # 创建工具栏
        self.create_toolbar()

        # 创建标签页控件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        # 标签页切换时更新导航按钮状态
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.content_layout.addWidget(self.tab_widget)

        # 将内容区域添加到主布局
        self.main_layout.addWidget(self.content_area, 1)

    def create_toolbar(self):
        """创建浏览器工具栏"""
        toolbar = QToolBar("导航工具栏")
        toolbar.setObjectName("mainToolbar")
        self.content_layout.addWidget(toolbar)

        # 后退按钮
        self.back_btn = QAction("后退", self)
        self.back_btn.triggered.connect(self.go_back)
        self.back_btn.setEnabled(False)  # 初始禁用
        toolbar.addAction(self.back_btn)

        # 前进按钮
        self.forward_btn = QAction("前进", self)
        self.forward_btn.triggered.connect(self.go_forward)
        self.forward_btn.setEnabled(False)  # 初始禁用
        toolbar.addAction(self.forward_btn)

        # 分隔线
        toolbar.addSeparator()

        # 打开MD文件按钮
        md_btn = QPushButton("打开MD文件")
        md_btn.clicked.connect(self.select_md_file)
        toolbar.addWidget(md_btn)

        # 选择本地文件按钮
        select_file_btn = QPushButton("选择本地文件")
        select_file_btn.clicked.connect(self.select_local_file)
        toolbar.addWidget(select_file_btn)

        # 新建标签页按钮
        new_tab_btn = QPushButton("+ 新标签")
        new_tab_btn.clicked.connect(self.create_new_tab)
        toolbar.addWidget(new_tab_btn)

        # 地址栏
        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        toolbar.addWidget(self.url_bar)

    def create_settings_tab(self):
        """创建设置标签页，包含关于信息"""
        # 创建设置主容器
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        
        # 创建标签页控件用于设置内部分类
        settings_tabs = QTabWidget()
        
        # 创建"关于"标签页
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        
        # 添加滚动区域以适应大量文本
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        
        # 关于信息文本
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml("""
        <h2 style="color:#3a7bd5;">关于 PennAicoin Browser</h2>
        <p><strong>版本:</strong> """ + self.browser_version + """</p>
        <hr>
        <h3>程序简介</h3>
        <p>PennAicoin Browser 是 PennAicoin 锦云策记账本的附属程序项目，专为辅助主程序查看和处理HTML、Markdown等文档内容而设计。</p>
        <p>本浏览器作为主程序的补充工具，提供了轻量级的网页浏览功能，特别优化了本地文件的查看体验，支持HTML文件直接打开和Markdown文档解析。</p>
        
        <h3>技术架构</h3>
        <p><strong>1. 浏览器内核</strong></p>
        <p>基于 Qt WebEngine 构建，该引擎采用 谷歌开源的Chromium 内核，支持现代Web标准：</p>
        <ul>
            <li>完整支持 HTML5 标准</li>
            <li>支持 JavaScript 执行环境</li>
            <li>支持 CSS3 样式渲染</li>
            <li>支持本地文件系统访问</li>
        </ul>
        
        <p><strong>2. GUI 构建框架</strong></p>
        <p>使用 PyQt5 框架构建用户界面：</p>
        <ul>
            <li>采用面向对象设计，组件化结构</li>
            <li>支持多标签页浏览模式</li>
            <li>使用 QSS (Qt Style Sheets) 进行样式定制，确保与主程序风格统一</li>
            <li>响应式布局设计，适应不同窗口大小</li>
        </ul>
        
        <p><strong>3. 功能特性</strong></p>
        <ul>
            <li>多标签页浏览环境</li>
            <li>本地HTML文件直接打开</li>
            <li>Markdown文档解析与显示</li>
            <li>前进/后退/刷新等标准导航功能</li>
            <li>自定义主页设置</li>
        </ul>
        
        <h3>版本说明</h3>
        <p>本浏览器版本独立于主程序，版本号格式为：</p>
        <p><em>PennAicoin_Browser_V[主版本].[次版本].[修订号].[年份].[月].[日].[构建号]</em></p>
        <p>当前版本为初始发布版本，提供基础浏览功能和记账本支持文档查看。</p>
        
        <h3>版权信息</h3>
        <p>&copy; 2025 wuhaung2@github </p>
        <p>本程序作为附属工具，随主程序一同发布和使用。</p>
        """)
        
        # 设置文本编辑框的样式
        about_text.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        
        scroll_layout.addWidget(about_text)
        scroll_area.setWidget(scroll_content)
        about_layout.addWidget(scroll_area)
        
        # 将"关于"标签页添加到设置标签页
        settings_tabs.addTab(about_tab, "关于")
        
        settings_layout.addWidget(settings_tabs)
        return settings_container

    def apply_styles(self):
        """应用与主程序统一的QSS样式"""
        self.setStyleSheet("""
            /* 全局样式 */
            QWidget {
                font-family: "Source Han Sans CN", "Noto Sans SC", sans-serif;
            }

            /* 主窗口 */
            QMainWindow {
                background-color: #f0f2f5;
            }

            /* 侧边导航栏 */
            #sidebar {
                background-color: white;
                border-right: 1px solid #e1e4e8;
            }

            /* 导航按钮 - 特别设置符号的大小和加粗 */
            #navButton {
                background-color: transparent;
                border: none;
                border-radius: 6px;
                color: #666;
                font-size: 20px;  /* 适当放大符号 */
                font-weight: bold;  /* 加粗显示 */
            }

            #navButton:hover {
                background-color: #eaecef;
                color: #3a7bd5;
            }

            #navButton:pressed {
                background-color: #d0d7de;
                color: #2a6bc5;
            }

            /* 工具栏 */
            #mainToolbar {
                background-color: white;
                border-bottom: 1px solid #e1e4e8;
                padding: 5px 10px;
                spacing: 10px;
            }

            /* 按钮样式 */
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

            /* 地址栏样式 */
            QLineEdit {
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 6px 8px;
                background-color: white;
                color: #2d3949;
                min-width: 400px;
            }

            QLineEdit:focus {
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

            /* 状态栏样式 */
            QStatusBar {
                background-color: white;
                border-top: 1px solid #e1e4e8;
                color: #666;
                padding: 4px 8px;
                font-size: 12px;
            }
            
            /* 设置页面标签 */
            QTabWidget QTabBar::tab {
                padding: 8px 20px;
            }
        """)

    def update_nav_buttons_state(self):
        """更新后退/前进按钮状态 - 增加类型检查"""
        current_widget = self.get_current_browser()
        
        # 检查当前标签页是否是浏览器标签页
        if isinstance(current_widget, CustomWebEngineView):
            history = current_widget.history()
            self.back_btn.setEnabled(history.canGoBack())
            self.forward_btn.setEnabled(history.canGoForward())
            # 启用地址栏
            self.url_bar.setEnabled(True)
        else:
            # 如果是设置页面或其他非浏览器页面，禁用导航按钮和地址栏
            self.back_btn.setEnabled(False)
            self.forward_btn.setEnabled(False)
            self.url_bar.setEnabled(False)

    def on_tab_changed(self, index):
        """标签页切换时更新导航按钮状态"""
        QTimer.singleShot(100, self.update_nav_buttons_state)

    def show_settings(self):
        """显示设置标签页"""
        # 检查设置标签页是否已存在
        if self.settings_tab is not None:
            self.tab_widget.setCurrentWidget(self.settings_tab)
            return
            
        # 创建设置标签页内容
        self.settings_tab = self.create_settings_tab()
        # 添加到标签页控件
        index = self.tab_widget.addTab(self.settings_tab, "设置")
        self.tab_widget.setCurrentIndex(index)
        # 标签页关闭时重置引用
        self.tab_widget.tabCloseRequested.connect(self.check_settings_tab_closed)

    def check_settings_tab_closed(self, index):
        """检查关闭的是否是设置标签页"""
        if self.tab_widget.widget(index) == self.settings_tab:
            self.settings_tab = None

    # 浏览器核心功能实现
    def navigate_home(self):
        """导航到主页"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView):
            self.load_url_in_browser(current_widget, self.home_page_path)

    def create_new_tab(self):
        """创建新标签页"""
        self.add_new_tab(title="新标签页")

    def go_back(self):
        """后退功能"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView) and current_widget.history().canGoBack():
            current_widget.back()
            QTimer.singleShot(100, self.update_nav_buttons_state)

    def go_forward(self):
        """前进功能"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView) and current_widget.history().canGoForward():
            current_widget.forward()
            QTimer.singleShot(100, self.update_nav_buttons_state)

    def select_md_file(self):
        """选择并显示本地Markdown文件"""
        current_widget = self.get_current_browser()
        if not isinstance(current_widget, CustomWebEngineView):
            self.statusBar().showMessage("请在浏览器标签页中执行此操作")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择MD文档", "", "Markdown文件 (*.md *.markdown);;所有文件 (*.*)"
        )
        if not file_path:
            return
    
        with open(file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        html_content = markdown.markdown(md_content)
        current_widget.setHtml(html_content)
        self.url_bar.setText(file_path)

    def enable_html5_features(self):
        """启用浏览器的HTML5相关特性"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView):
            settings = current_widget.page().settings()
            settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

    def load_start_page(self):
        """加载默认主页"""
        self.add_new_tab(url=self.home_page_path)

    def add_new_tab(self, browser=None, url=None, title="新标签页"):
        """添加新的浏览器标签页"""
        if not browser:
            browser = CustomWebEngineView(self)
            browser.urlChanged.connect(self.update_url_bar)
            browser.titleChanged.connect(self.update_tab_title)
            browser.loadStarted.connect(lambda: self.statusBar().showMessage("加载中..."))
            browser.loadFinished.connect(lambda: self.statusBar().showMessage("加载完成"))
            browser.page().linkHovered.connect(self.show_link_info)

        if url:
            self.load_url_in_browser(browser, url)
        else:
            self.load_url_in_browser(browser, self.home_page_path)

        index = self.tab_widget.addTab(browser, title)
        self.tab_widget.setCurrentIndex(index)
        return index

    def close_tab(self, index):
        """关闭标签页"""
        if self.tab_widget.count() > 1:
            widget_to_remove = self.tab_widget.widget(index)
            # 如果关闭的是设置标签页，重置引用
            if widget_to_remove == self.settings_tab:
                self.settings_tab = None
            self.tab_widget.removeTab(index)
        else:
            self.close()

    def get_current_browser(self):
        """获取当前活动的标签页"""
        return self.tab_widget.currentWidget()

    def refresh_page(self):
        """刷新当前页面"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView):
            current_widget.reload()
        else:
            self.statusBar().showMessage("设置页面无需刷新")

    def navigate_to_url(self):
        """根据地址栏内容导航"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView):
            url_text = self.url_bar.text().strip()
            if url_text.startswith(('http://', 'https://')):
                current_widget.setUrl(QUrl(url_text))
            else:
                local_url = QUrl.fromLocalFile(url_text)
                if local_url.isValid():
                    current_widget.setUrl(local_url)
                else:
                    self.statusBar().showMessage("无效的路径或URL")
        else:
            self.statusBar().showMessage("请在浏览器标签页中输入网址")

    def update_url_bar(self, qurl):
        """更新地址栏显示"""
        current_widget = self.get_current_browser()
        if isinstance(current_widget, CustomWebEngineView):
            self.url_bar.setText(qurl.toString())
            self.url_bar.setCursorPosition(0)

    def update_tab_title(self, title):
        """更新标签页标题"""
        index = self.tab_widget.currentIndex()
        if len(title) > 20:
            title = title[:20] + "..."
        self.tab_widget.setTabText(index, title)

    def load_url_in_browser(self, browser, url):
        """在指定浏览器中加载URL或本地文件"""
        if isinstance(url, str):
            if url.startswith(('http://', 'https://')):
                browser.setUrl(QUrl(url))
            else:
                local_url = QUrl.fromLocalFile(url)
                if local_url.isValid():
                    browser.setUrl(local_url)
                else:
                    self.statusBar().showMessage(f"无效的文件路径: {url}")

    def show_link_info(self, url):
        """在状态栏显示鼠标悬停的链接"""
        if url:
            self.statusBar().showMessage(url)
        else:
            self.statusBar().clearMessage()

    def select_local_file(self):
        """选择并显示本地文件"""
        current_widget = self.get_current_browser()
        if not isinstance(current_widget, CustomWebEngineView):
            self.statusBar().showMessage("请在浏览器标签页中执行此操作")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择本地文件", "", "HTML文件 (*.html);;所有文件 (*.*)"
        )
        if file_path:
            self.load_url_in_browser(current_widget, file_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Source Han Sans CN", 10)
    app.setFont(font)
    
    browser = PennaicoinBrowser()
    browser.show()
    sys.exit(app.exec_())

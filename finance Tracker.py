import sqlite3
import csv
import calendar
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Matplotlib imports for Tkinter embedding
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class FinanceDatabase:
    """Handles SQLite database operations with clean ID sequence management."""
    def __init__(self, db_name="finance_tracker.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                account TEXT NOT NULL DEFAULT 'Bank',
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT
            )
        """)

        # Auto-migrate existing databases without the 'account' column
        self.cursor.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in self.cursor.fetchall()]
        if "account" not in columns:
            self.cursor.execute("ALTER TABLE transactions ADD COLUMN account TEXT NOT NULL DEFAULT 'Bank'")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS recurring_bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                account TEXT NOT NULL DEFAULT 'Bank',
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                due_day INTEGER NOT NULL,
                last_paid_month TEXT DEFAULT ''
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('monthly_budget', '50000.0')"
        )
        self.conn.commit()

    def _reset_sequence_if_empty(self, table_name):
        """Resets AUTOINCREMENT counter to 0 when all rows in a table are deleted."""
        self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))

    def add_transaction(self, date_str, account, t_type, category, amount, description):
        self.cursor.execute(
            "INSERT INTO transactions (date, account, type, category, amount, description) VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, account, t_type, category, amount, description)
        )
        self.conn.commit()

    def delete_transaction(self, transaction_id):
        self.cursor.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
        self._reset_sequence_if_empty("transactions")
        self.conn.commit()

    def get_transactions(self, filter_account="All", filter_type="All", filter_category="All"):
        query = "SELECT id, date, account, type, category, amount, description FROM transactions WHERE 1=1"
        params = []

        if filter_account != "All":
            query += " AND account = ?"
            params.append(filter_account)
        if filter_type != "All":
            query += " AND type = ?"
            params.append(filter_type)
        if filter_category != "All":
            query += " AND category = ?"
            params.append(filter_category)

        query += " ORDER BY date DESC, id DESC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    # --- RECURRING BILLS METHODS ---
    def add_recurring_bill(self, name, account, category, amount, due_day):
        self.cursor.execute(
            "INSERT INTO recurring_bills (name, account, category, amount, due_day, last_paid_month) VALUES (?, ?, ?, ?, ?, '')",
            (name, account, category, amount, due_day)
        )
        self.conn.commit()

    def get_recurring_bills(self):
        self.cursor.execute(
            "SELECT id, name, account, category, amount, due_day, last_paid_month FROM recurring_bills ORDER BY due_day ASC"
        )
        return self.cursor.fetchall()

    def pay_recurring_bill(self, bill_id):
        self.cursor.execute(
            "SELECT name, account, category, amount FROM recurring_bills WHERE id = ?",
            (int(bill_id),)
        )
        bill = self.cursor.fetchone()
        if not bill:
            return False

        name, account, category, amount = bill
        today_str = datetime.now().strftime("%Y-%m-%d")
        current_ym = datetime.now().strftime("%Y-%m")

        self.add_transaction(today_str, account, "Expense", category, amount, f"Recurring Bill: {name}")
        self.cursor.execute(
            "UPDATE recurring_bills SET last_paid_month = ? WHERE id = ?",
            (current_ym, int(bill_id))
        )
        self.conn.commit()
        return True

    def delete_recurring_bill(self, bill_id):
        self.cursor.execute("DELETE FROM recurring_bills WHERE id = ?", (int(bill_id),))
        self._reset_sequence_if_empty("recurring_bills")
        self.conn.commit()

    # --- ANALYTICS & BALANCES ---
    def get_account_balances(self):
        balances = {"Bank": 0.0, "Cash": 0.0, "Credit Card": 0.0}
        self.cursor.execute("""
            SELECT account,
                   SUM(CASE WHEN type = 'Income' THEN amount ELSE -amount END)
            FROM transactions
            GROUP BY account
        """)
        for acc, net in self.cursor.fetchall():
            if acc in balances:
                balances[acc] = net or 0.0
        return balances

    def get_summary(self):
        self.cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'Income'")
        income = self.cursor.fetchone()[0] or 0.0

        self.cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'Expense'")
        expense = self.cursor.fetchone()[0] or 0.0

        current_month = datetime.now().strftime("%Y-%m")
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE type = 'Expense' AND date LIKE ?",
            (f"{current_month}%",)
        )
        month_expense = self.cursor.fetchone()[0] or 0.0

        return income, expense, income - expense, month_expense

    def get_category_breakdown(self):
        self.cursor.execute("""
            SELECT category, SUM(amount) 
            FROM transactions 
            WHERE type = 'Expense' 
            GROUP BY category 
            ORDER BY SUM(amount) DESC
        """)
        return self.cursor.fetchall()

    def get_monthly_trends(self):
        self.cursor.execute("""
            SELECT substr(date, 1, 7) AS month,
                   SUM(CASE WHEN type = 'Income' THEN amount ELSE 0 END) AS total_income,
                   SUM(CASE WHEN type = 'Expense' THEN amount ELSE 0 END) AS total_expense
            FROM transactions
            GROUP BY month
            ORDER BY month ASC
            LIMIT 6
        """)
        return self.cursor.fetchall()

    def get_budget(self):
        self.cursor.execute("SELECT value FROM settings WHERE key = 'monthly_budget'")
        res = self.cursor.fetchone()
        return float(res[0]) if res else 50000.0

    def set_budget(self, amount):
        self.cursor.execute(
            "REPLACE INTO settings (key, value) VALUES ('monthly_budget', ?)",
            (str(amount),)
        )
        self.conn.commit()


class FinanceTrackerApp:
    """Trendy Modern Dark Fintech Dashboard with Sequential ID Display (Python 3.14)."""
    ACCOUNTS = ["Bank", "Cash", "Credit Card"]
    CATEGORIES = [
        "Salary", "Freelance", "Investments", "Food & Dining",
        "Rent & Utilities", "Subscriptions", "Transport", "Shopping",
        "Healthcare", "Entertainment", "Credit Card Payment", "Savings", "Other"
    ]

    # Modern Fintech Dark Palette
    BG_OBSIDIAN = "#0b0f19"
    BG_SURFACE = "#111827"
    BG_INPUT = "#1f2937"
    BORDER_SUBTLE = "#263042"
    TEXT_PRIMARY = "#f8fafc"
    TEXT_MUTED = "#94a3b8"

    NEON_CYAN = "#06b6d4"
    NEON_MINT = "#10b981"
    NEON_AMBER = "#f59e0b"
    NEON_VIOLET = "#8b5cf6"
    NEON_ROSE = "#f43f5e"

    def __init__(self, root):
        self.root = root
        self.root.title("NOVA WEALTH  |  Personal Finance & Recurring Bills")
        self.root.geometry("1320x800")
        self.root.minsize(1120, 700)
        self.root.configure(bg=self.BG_OBSIDIAN)

        self.db = FinanceDatabase()
        self.pie_wedges = []
        self.pie_labels = []
        self.pie_values = []
        self.bar_rects = []

        self.setup_styles()
        self.build_ui()
        self.refresh_data()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "TCombobox",
            fieldbackground=self.BG_INPUT,
            background="#374151",
            foreground=self.TEXT_PRIMARY,
            arrowcolor=self.NEON_CYAN,
            bordercolor=self.BORDER_SUBTLE,
            lightcolor=self.BG_INPUT,
            darkcolor=self.BG_INPUT
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.BG_INPUT)],
            foreground=[("readonly", self.TEXT_PRIMARY)],
            selectbackground=[("readonly", self.NEON_VIOLET)],
            selectforeground=[("readonly", "#ffffff")]
        )

        style.configure(
            "Treeview",
            background=self.BG_SURFACE,
            foreground=self.TEXT_PRIMARY,
            fieldbackground=self.BG_SURFACE,
            rowheight=32,
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#1e293b",
            foreground=self.NEON_CYAN,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=6
        )
        style.map("Treeview.Heading", background=[("active", "#334155")])
        style.map(
            "Treeview",
            background=[("selected", "#312e81")],
            foreground=[("selected", "#ffffff")]
        )

        style.configure("TNotebook", background=self.BG_OBSIDIAN, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.BG_INPUT,
            foreground=self.TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            padding=[16, 9],
            borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.NEON_VIOLET)],
            foreground=[("selected", "#ffffff")]
        )

    def build_ui(self):
        # --- 1. TOP NAVBAR ---
        navbar = tk.Frame(self.root, bg=self.BG_SURFACE, height=62, padx=22)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=self.BG_SURFACE)
        brand_frame.pack(side="left", pady=14)

        tk.Label(
            brand_frame, text="◆", bg=self.BG_SURFACE, fg=self.NEON_CYAN, font=("Segoe UI", 16, "bold")
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            brand_frame, text="NOVA", bg=self.BG_SURFACE, fg="#ffffff", font=("Segoe UI", 15, "bold")
        ).pack(side="left")

        tk.Label(
            brand_frame, text="FINANCE", bg=self.BG_SURFACE, fg=self.NEON_VIOLET, font=("Segoe UI", 15, "bold")
        ).pack(side="left", padx=(4, 14))

        tk.Label(
            brand_frame, text="PORTFOLIO • CASHFLOW • SUBSCRIPTIONS", bg="#1e293b", fg=self.TEXT_MUTED,
            font=("Segoe UI", 8, "bold"), padx=10, pady=3
        ).pack(side="left")

        right_nav = tk.Frame(navbar, bg=self.BG_SURFACE)
        right_nav.pack(side="right", pady=15)

        self.lbl_bill_alert = tk.Label(
            right_nav,
            text="✓ ALL BILLS CLEAR",
            bg="#064e3b",
            fg="#34d399",
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=5,
            cursor="hand2"
        )
        self.lbl_bill_alert.pack(side="left", padx=(0, 10))
        self.lbl_bill_alert.bind("<Button-1>", lambda e: self.notebook.select(self.tab_bills))

        tk.Label(
            right_nav,
            text=f"●  {datetime.now().strftime('%d %b %Y')}",
            bg="#1e1b4b",
            fg="#a5b4fc",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=5
        ).pack(side="left")

        tk.Frame(self.root, bg=self.NEON_VIOLET, height=2).pack(fill="x")

        # --- 2. GLOWING KPI SUMMARY CARDS ---
        cards_row = tk.Frame(self.root, bg=self.BG_OBSIDIAN, padx=16, pady=14)
        cards_row.pack(fill="x")

        self.lbl_bank = self.create_neon_card(
            cards_row, "BANK ACCOUNT", "₹ 0.00", accent=self.NEON_CYAN, badge="SAVINGS / CHECKING", col=0
        )
        self.lbl_cash = self.create_neon_card(
            cards_row, "CASH WALLET", "₹ 0.00", accent=self.NEON_MINT, badge="LIQUID CASH", col=1
        )
        self.lbl_cc = self.create_neon_card(
            cards_row, "CREDIT CARD", "₹ 0.00", accent=self.NEON_AMBER, badge="CREDIT LINE", col=2
        )
        self.lbl_balance = self.create_neon_card(
            cards_row, "NET WORTH", "₹ 0.00", accent=self.NEON_VIOLET, badge="TOTAL ASSETS", col=3
        )
        self.lbl_budget = self.create_neon_card(
            cards_row, "MONTHLY BUDGET", "₹ 0 / ₹ 0", accent=self.NEON_ROSE, badge="SPEND LIMIT", col=4
        )

        for i in range(5):
            cards_row.columnconfigure(i, weight=1)

        # --- 3. MAIN WORKSPACE ---
        workspace = tk.Frame(self.root, bg=self.BG_OBSIDIAN, padx=16)
        workspace.pack(fill="both", expand=True, pady=(0, 16))

        left_panel = tk.Frame(workspace, bg=self.BG_OBSIDIAN, width=330)
        left_panel.pack(side="left", fill="y", padx=(0, 16))
        left_panel.pack_propagate(False)

        self.build_entry_form(left_panel)
        self.build_budget_box(left_panel)

        right_panel = tk.Frame(workspace, bg=self.BG_OBSIDIAN)
        right_panel.pack(side="right", fill="both", expand=True)

        self.notebook = ttk.Notebook(right_panel)
        self.notebook.pack(fill="both", expand=True)

        self.tab_table = tk.Frame(self.notebook, bg=self.BG_SURFACE, padx=14, pady=14)
        self.tab_bills = tk.Frame(self.notebook, bg=self.BG_SURFACE, padx=14, pady=14)
        self.tab_charts = tk.Frame(self.notebook, bg=self.BG_SURFACE, padx=14, pady=14)

        self.notebook.add(self.tab_table, text="  ⚡ TRANSACTIONS LEDGER  ")
        self.notebook.add(self.tab_bills, text="  🔄 RECURRING BILLS & SUBS  ")
        self.notebook.add(self.tab_charts, text="  📊 VISUAL ANALYTICS  ")

        self.build_table_area(self.tab_table)
        self.build_bills_area(self.tab_bills)
        self.build_charts_area(self.tab_charts)

    def create_neon_card(self, parent, title, initial_val, accent, badge, col):
        outer = tk.Frame(
            parent, bg=self.BG_SURFACE,
            highlightbackground=self.BORDER_SUBTLE, highlightthickness=1
        )
        outer.grid(row=0, column=col, sticky="ew", padx=6)

        tk.Frame(outer, bg=accent, width=4).pack(side="left", fill="y")

        body = tk.Frame(outer, bg=self.BG_SURFACE, padx=12, pady=10)
        body.pack(side="left", fill="both", expand=True)

        top_row = tk.Frame(body, bg=self.BG_SURFACE)
        top_row.pack(fill="x")

        tk.Label(
            top_row, text=title, bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")
        ).pack(side="left")

        tk.Label(
            top_row, text=badge, bg=self.BG_INPUT, fg=accent, font=("Segoe UI", 7, "bold"), padx=6, pady=1
        ).pack(side="right")

        lbl_val = tk.Label(
            body, text=initial_val, bg=self.BG_SURFACE, fg=self.TEXT_PRIMARY, font=("Segoe UI", 14, "bold")
        )
        lbl_val.pack(anchor="w", pady=(6, 0))
        return lbl_val

    def create_dark_entry(self, parent, default_text=""):
        ent = tk.Entry(
            parent,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.NEON_CYAN,
            relief="flat",
            font=("Segoe UI", 10),
            highlightbackground=self.BORDER_SUBTLE,
            highlightcolor=self.NEON_CYAN,
            highlightthickness=1
        )
        if default_text:
            ent.insert(0, default_text)
        return ent

    def build_entry_form(self, parent):
        card = tk.Frame(
            parent, bg=self.BG_SURFACE,
            highlightbackground=self.BORDER_SUBTLE, highlightthickness=1
        )
        card.pack(fill="x", pady=(0, 14))

        header = tk.Frame(card, bg="#182032", padx=14, pady=10)
        header.pack(fill="x")
        tk.Label(
            header, text="＋ NEW TRANSACTION", bg="#182032", fg=self.NEON_CYAN,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left")

        form = tk.Frame(card, bg=self.BG_SURFACE, padx=14, pady=12)
        form.pack(fill="x")

        tk.Label(form, text="Flow Type", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=6)
        self.var_type = tk.StringVar(value="Expense")
        rb_frame = tk.Frame(form, bg=self.BG_SURFACE)
        rb_frame.grid(row=0, column=1, sticky="w", pady=6)

        tk.Radiobutton(
            rb_frame, text="Expense", variable=self.var_type, value="Expense",
            bg=self.BG_SURFACE, fg=self.NEON_ROSE, activebackground=self.BG_SURFACE,
            activeforeground=self.NEON_ROSE, selectcolor=self.BG_INPUT, font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 12))

        tk.Radiobutton(
            rb_frame, text="Income", variable=self.var_type, value="Income",
            bg=self.BG_SURFACE, fg=self.NEON_MINT, activebackground=self.BG_SURFACE,
            activeforeground=self.NEON_MINT, selectcolor=self.BG_INPUT, font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        tk.Label(form, text="Account", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=6)
        self.cmb_account = ttk.Combobox(form, values=self.ACCOUNTS, state="readonly")
        self.cmb_account.set("Bank")
        self.cmb_account.grid(row=1, column=1, sticky="ew", pady=6)

        tk.Label(form, text="Date", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=6)
        self.ent_date = self.create_dark_entry(form, datetime.now().strftime("%Y-%m-%d"))
        self.ent_date.grid(row=2, column=1, sticky="ew", pady=6, ipady=4)

        tk.Label(form, text="Category", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=6)
        self.cmb_category = ttk.Combobox(form, values=self.CATEGORIES, state="readonly")
        self.cmb_category.set("Food & Dining")
        self.cmb_category.grid(row=3, column=1, sticky="ew", pady=6)

        tk.Label(form, text="Amount (₹)", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=4, column=0, sticky="w", pady=6)
        self.ent_amount = self.create_dark_entry(form)
        self.ent_amount.grid(row=4, column=1, sticky="ew", pady=6, ipady=4)

        tk.Label(form, text="Note", bg=self.BG_SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=5, column=0, sticky="w", pady=6)
        self.ent_desc = self.create_dark_entry(form)
        self.ent_desc.grid(row=5, column=1, sticky="ew", pady=6, ipady=4)

        btn_add = tk.Button(
            form, text="RECORD TRANSACTION", command=self.add_transaction,
            bg=self.NEON_VIOLET, fg="#ffffff", activebackground="#7c3aed", activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat", pady=8, cursor="hand2"
        )
        btn_add.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        form.columnconfigure(1, weight=1)

    def build_budget_box(self, parent):
        card = tk.Frame(
            parent, bg=self.BG_SURFACE,
            highlightbackground=self.BORDER_SUBTLE, highlightthickness=1
        )
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg="#182032", padx=14, pady=10)
        header.pack(fill="x")
        tk.Label(
            header, text="🎯 MONTHLY SPEND CAP", bg="#182032", fg=self.NEON_AMBER,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left")

        body = tk.Frame(card, bg=self.BG_SURFACE, padx=14, pady=12)
        body.pack(fill="both", expand=True)

        budget_row = tk.Frame(body, bg=self.BG_SURFACE)
        budget_row.pack(fill="x", pady=(0, 12))

        self.ent_budget = self.create_dark_entry(budget_row, str(self.db.get_budget()))
        self.ent_budget.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)

        tk.Button(
            budget_row, text="UPDATE", command=self.update_budget,
            bg=self.NEON_CYAN, fg="#0b0f19", activebackground="#0891b2", activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right")

        tip_box = tk.Frame(
            body, bg=self.BG_INPUT, padx=12, pady=10,
            highlightbackground=self.BORDER_SUBTLE, highlightthickness=1
        )
        tip_box.pack(fill="both", expand=True)

        tip_text = (
            "• Recurring Bills: Open the 'RECURRING BILLS & SUBS' tab to track monthly rent, EMIs, and subscriptions.\n\n"
            "• Sequential IDs: Table rows automatically re-number cleanly (1, 2, 3...) whenever items are added or deleted."
        )
        tk.Label(
            tip_box, text=tip_text, bg=self.BG_INPUT, fg=self.TEXT_MUTED,
            font=("Segoe UI", 9), wraplength=260, justify="left"
        ).pack(anchor="nw")

    def build_table_area(self, parent):
        filter_bar = tk.Frame(parent, bg=self.BG_INPUT, padx=12, pady=10)
        filter_bar.pack(fill="x", pady=(0, 12))

        tk.Label(filter_bar, text="Account:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.cmb_filter_acc = ttk.Combobox(filter_bar, values=["All"] + self.ACCOUNTS, state="readonly", width=11)
        self.cmb_filter_acc.set("All")
        self.cmb_filter_acc.pack(side="left", padx=(0, 12))
        self.cmb_filter_acc.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())

        tk.Label(filter_bar, text="Type:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.cmb_filter_type = ttk.Combobox(filter_bar, values=["All", "Income", "Expense"], state="readonly", width=9)
        self.cmb_filter_type.set("All")
        self.cmb_filter_type.pack(side="left", padx=(0, 12))
        self.cmb_filter_type.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())

        tk.Label(filter_bar, text="Category:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.cmb_filter_cat = ttk.Combobox(filter_bar, values=["All"] + self.CATEGORIES, state="readonly", width=15)
        self.cmb_filter_cat.set("All")
        self.cmb_filter_cat.pack(side="left", padx=(0, 12))
        self.cmb_filter_cat.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())

        tk.Button(
            filter_bar, text="EXPORT CSV", command=self.export_csv,
            bg=self.NEON_CYAN, fg="#0b0f19", activebackground="#0891b2", activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            filter_bar, text="DELETE", command=self.delete_selected,
            bg=self.NEON_ROSE, fg="#ffffff", activebackground="#be123c", activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right")

        columns = ("ID", "Date", "Account", "Type", "Category", "Amount", "Description")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")

        col_widths = {
            "ID": 45, "Date": 95, "Account": 95, "Type": 75,
            "Category": 140, "Amount": 115, "Description": 220
        }
        for col in columns:
            self.tree.heading(col, text=col.upper())
            anchor = "e" if col == "Amount" else ("center" if col in ("ID", "Date", "Account", "Type") else "w")
            self.tree.column(col, width=col_widths[col], anchor=anchor)

        self.tree.tag_configure("Income_even", foreground="#34d399", background="#111827")
        self.tree.tag_configure("Income_odd", foreground="#34d399", background="#161f33")
        self.tree.tag_configure("Expense_even", foreground="#fb7185", background="#111827")
        self.tree.tag_configure("Expense_odd", foreground="#fb7185", background="#161f33")

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def build_bills_area(self, parent):
        """Builds the Recurring Monthly Bills & Subscriptions Manager."""
        add_bar = tk.Frame(
            parent, bg=self.BG_INPUT, padx=12, pady=10,
            highlightbackground=self.BORDER_SUBTLE, highlightthickness=1
        )
        add_bar.pack(fill="x", pady=(0, 12))

        tk.Label(add_bar, text="Bill Name:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.ent_bill_name = self.create_dark_entry(add_bar)
        self.ent_bill_name.grid(row=1, column=0, sticky="ew", padx=(0, 8), ipady=3)

        tk.Label(add_bar, text="Account:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", padx=(0, 4))
        self.cmb_bill_acc = ttk.Combobox(add_bar, values=self.ACCOUNTS, state="readonly", width=11)
        self.cmb_bill_acc.set("Bank")
        self.cmb_bill_acc.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        tk.Label(add_bar, text="Category:", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", padx=(0, 4))
        self.cmb_bill_cat = ttk.Combobox(add_bar, values=self.CATEGORIES, state="readonly", width=14)
        self.cmb_bill_cat.set("Subscriptions")
        self.cmb_bill_cat.grid(row=1, column=2, sticky="ew", padx=(0, 8))

        tk.Label(add_bar, text="Amount (₹):", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=3, sticky="w", padx=(0, 4))
        self.ent_bill_amt = self.create_dark_entry(add_bar)
        self.ent_bill_amt.configure(width=11)
        self.ent_bill_amt.grid(row=1, column=3, sticky="ew", padx=(0, 8), ipady=3)

        tk.Label(add_bar, text="Due Day (1-31):", bg=self.BG_INPUT, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=4, sticky="w", padx=(0, 4))
        self.ent_bill_day = self.create_dark_entry(add_bar, "5")
        self.ent_bill_day.configure(width=8)
        self.ent_bill_day.grid(row=1, column=4, sticky="ew", padx=(0, 10), ipady=3)

        tk.Button(
            add_bar, text="+ ADD BILL", command=self.add_bill,
            bg=self.NEON_VIOLET, fg="#ffffff", activebackground="#7c3aed", activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=12, pady=5, cursor="hand2"
        ).grid(row=1, column=5, sticky="ew")

        add_bar.columnconfigure(0, weight=2)

        action_bar = tk.Frame(parent, bg=self.BG_SURFACE, pady=6)
        action_bar.pack(fill="x", pady=(0, 8))

        self.lbl_bills_summary = tk.Label(
            action_bar,
            text="Monthly Fixed Commitments: ₹ 0.00  |  Remaining Unpaid: ₹ 0.00",
            bg=self.BG_SURFACE,
            fg=self.NEON_CYAN,
            font=("Segoe UI", 9, "bold")
        )
        self.lbl_bills_summary.pack(side="left")

        tk.Button(
            action_bar, text="REMOVE BILL", command=self.delete_bill,
            bg=self.NEON_ROSE, fg="#ffffff", activebackground="#be123c", activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            action_bar, text="✓ PAY SELECTED BILL", command=self.pay_selected_bill,
            bg=self.NEON_MINT, fg="#0b0f19", activebackground="#059669", activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=14, pady=4, cursor="hand2"
        ).pack(side="right")

        bill_cols = ("ID", "Bill / Subscription", "Account", "Category", "Amount", "Due Date", "Status")
        self.bills_tree = ttk.Treeview(parent, columns=bill_cols, show="headings", selectmode="browse")

        b_widths = {
            "ID": 45, "Bill / Subscription": 175, "Account": 95,
            "Category": 135, "Amount": 110, "Due Date": 125, "Status": 130
        }
        for col in bill_cols:
            self.bills_tree.heading(col, text=col.upper())
            anchor = "e" if col == "Amount" else ("center" if col in ("ID", "Account", "Due Date", "Status") else "w")
            self.bills_tree.column(col, width=b_widths[col], anchor=anchor)

        self.bills_tree.tag_configure("PAID", foreground="#34d399", background="#111827")
        self.bills_tree.tag_configure("OVERDUE", foreground="#fb7185", background="#28131d")
        self.bills_tree.tag_configure("DUE_SOON", foreground="#fbbf24", background="#261f11")
        self.bills_tree.tag_configure("UPCOMING", foreground="#38bdf8", background="#111827")

        b_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.bills_tree.yview)
        self.bills_tree.configure(yscrollcommand=b_scroll.set)

        self.bills_tree.pack(side="left", fill="both", expand=True)
        b_scroll.pack(side="right", fill="y")

    def build_charts_area(self, parent):
        self.fig = Figure(figsize=(8.8, 5.0), dpi=100, facecolor=self.BG_SURFACE)
        self.ax_pie = self.fig.add_subplot(121)
        self.ax_bar = self.fig.add_subplot(122)
        self.fig.subplots_adjust(wspace=0.35, left=0.06, right=0.96, top=0.86, bottom=0.16)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        self.tooltip = self.fig.text(
            0, 0, "", color="#ffffff", fontsize=9, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#1e1b4b", edgecolor=self.NEON_CYAN, lw=1.5),
            visible=False
        )
        self.canvas.mpl_connect("motion_notify_event", self.on_chart_hover)

        toolbar_frame = tk.Frame(parent, bg=self.BG_INPUT)
        toolbar_frame.pack(fill="x")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.config(background=self.BG_INPUT)
        for button in self.toolbar.winfo_children():
            button.config(background=self.BG_INPUT)
        self.toolbar.update()

    def on_chart_hover(self, event):
        if event.inaxes == self.ax_pie and self.pie_wedges:
            for idx, wedge in enumerate(self.pie_wedges):
                contains, _ = wedge.contains(event)
                if contains:
                    fig_x, fig_y = self.fig.transFigure.inverted().transform((event.x, event.y))
                    self.tooltip.set_position((min(fig_x + 0.02, 0.78), min(fig_y + 0.02, 0.90)))
                    self.tooltip.set_text(f"{self.pie_labels[idx]}\n₹ {self.pie_values[idx]:,.2f}")
                    self.tooltip.set_visible(True)
                    self.canvas.draw_idle()
                    return

        elif event.inaxes == self.ax_bar and self.bar_rects:
            for rect, label, val in self.bar_rects:
                contains, _ = rect.contains(event)
                if contains:
                    fig_x, fig_y = self.fig.transFigure.inverted().transform((event.x, event.y))
                    self.tooltip.set_position((min(fig_x + 0.02, 0.78), min(fig_y + 0.02, 0.90)))
                    self.tooltip.set_text(f"{label}\n₹ {val:,.2f}")
                    self.tooltip.set_visible(True)
                    self.canvas.draw_idle()
                    return

        if self.tooltip.get_visible():
            self.tooltip.set_visible(False)
            self.canvas.draw_idle()

    def update_charts(self):
        self.ax_pie.clear()
        self.ax_bar.clear()
        self.pie_wedges = []
        self.pie_labels = []
        self.pie_values = []
        self.bar_rects = []

        self.ax_pie.set_facecolor(self.BG_SURFACE)
        self.ax_bar.set_facecolor(self.BG_SURFACE)

        breakdown = self.db.get_category_breakdown()
        if breakdown:
            categories = [row[0] for row in breakdown]
            amounts = [row[1] for row in breakdown]
            neon_palette = [
                "#06b6d4", "#8b5cf6", "#f43f5e", "#10b981", "#f59e0b",
                "#3b82f6", "#ec4899", "#14b8a6", "#a855f7", "#eab308"
            ]

            wedges, texts, autotexts = self.ax_pie.pie(
                amounts,
                labels=categories,
                autopct="%1.1f%%",
                startangle=140,
                colors=neon_palette[:len(categories)],
                pctdistance=0.78,
                wedgeprops={"width": 0.44, "edgecolor": self.BG_SURFACE, "linewidth": 2.5},
                textprops={"fontsize": 8.5, "color": self.TEXT_PRIMARY, "fontweight": "bold"}
            )
            for autotext in autotexts:
                autotext.set_color("#0b0f19")
                autotext.set_fontweight("bold")
                autotext.set_fontsize(8)

            self.pie_wedges = wedges
            self.pie_labels = categories
            self.pie_values = amounts

            self.ax_pie.set_title("EXPENSE ALLOCATION", fontsize=11, fontweight="bold", color=self.NEON_CYAN, pad=14)
        else:
            self.ax_pie.text(0.5, 0.5, "No Expense Data Yet", ha="center", va="center", fontsize=10, color=self.TEXT_MUTED)
            self.ax_pie.set_title("EXPENSE ALLOCATION", fontsize=11, fontweight="bold", color=self.NEON_CYAN)
            self.ax_pie.axis("off")

        trends = self.db.get_monthly_trends()
        if trends:
            months = [row[0] for row in trends]
            incomes = [row[1] for row in trends]
            expenses = [row[2] for row in trends]

            x = range(len(months))
            width = 0.36

            bars_inc = self.ax_bar.bar([i - width/2 for i in x], incomes, width, label="Income", color=self.NEON_MINT)
            bars_exp = self.ax_bar.bar([i + width/2 for i in x], expenses, width, label="Expense", color=self.NEON_ROSE)

            for m, rect in zip(months, bars_inc):
                self.bar_rects.append((rect, f"{m} Income", rect.get_height()))
            for m, rect in zip(months, bars_exp):
                self.bar_rects.append((rect, f"{m} Expense", rect.get_height()))

            self.ax_bar.set_xticks(list(x))
            self.ax_bar.set_xticklabels(months, rotation=25, fontsize=8.5, color=self.TEXT_MUTED)
            self.ax_bar.tick_params(axis="y", colors=self.TEXT_MUTED, labelsize=8.5)
            self.ax_bar.set_title("MONTHLY CASHFLOW", fontsize=11, fontweight="bold", color=self.NEON_VIOLET, pad=14)
            self.ax_bar.legend(frameon=True, facecolor=self.BG_INPUT, edgecolor=self.BORDER_SUBTLE, labelcolor=self.TEXT_PRIMARY, fontsize=8.5)
            self.ax_bar.grid(axis="y", linestyle="--", alpha=0.25, color="#64748b")
            self.ax_bar.spines["top"].set_visible(False)
            self.ax_bar.spines["right"].set_visible(False)
            self.ax_bar.spines["left"].set_color(self.BORDER_SUBTLE)
            self.ax_bar.spines["bottom"].set_color(self.BORDER_SUBTLE)

            for bar in bars_inc:
                h = bar.get_height()
                if h > 0:
                    self.ax_bar.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width()/2, h),
                                         xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7.5, color="#34d399", fontweight="bold")
            for bar in bars_exp:
                h = bar.get_height()
                if h > 0:
                    self.ax_bar.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width()/2, h),
                                         xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7.5, color="#fb7185", fontweight="bold")
        else:
            self.ax_bar.text(0.5, 0.5, "No Monthly Data Yet", ha="center", va="center", fontsize=10, color=self.TEXT_MUTED)
            self.ax_bar.set_title("MONTHLY CASHFLOW", fontsize=11, fontweight="bold", color=self.NEON_VIOLET)
            self.ax_bar.axis("off")

        self.canvas.draw()

    # --- ACTIONS ---
    def add_transaction(self):
        t_type = self.var_type.get()
        account = self.cmb_account.get()
        date_str = self.ent_date.get().strip()
        category = self.cmb_category.get()
        amount_str = self.ent_amount.get().strip()
        desc = self.ent_desc.get().strip()

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid Date", "Please enter the date in YYYY-MM-DD format.")
            return

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Amount", "Please enter a valid positive number for the amount.")
            return

        self.db.add_transaction(date_str, account, t_type, category, amount, desc)
        self.ent_amount.delete(0, tk.END)
        self.ent_desc.delete(0, tk.END)
        self.refresh_data()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a transaction from the table to delete.")
            return

        # selected[0] holds the exact SQLite primary key (iid), while values[0] is the display row number
        db_id = selected[0]
        display_num = self.tree.item(db_id)["values"][0]

        if messagebox.askyesno("Confirm Delete", f"Delete transaction #{display_num}?"):
            self.db.delete_transaction(db_id)
            self.refresh_data()

    def add_bill(self):
        name = self.ent_bill_name.get().strip()
        account = self.cmb_bill_acc.get()
        category = self.cmb_bill_cat.get()
        amt_str = self.ent_bill_amt.get().strip()
        day_str = self.ent_bill_day.get().strip()

        if not name:
            messagebox.showerror("Missing Name", "Please enter a name for the bill or subscription.")
            return

        try:
            amount = float(amt_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Amount", "Please enter a valid positive amount.")
            return

        try:
            due_day = int(day_str)
            if not (1 <= due_day <= 31):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Due Day", "Please enter a day of the month between 1 and 31.")
            return

        self.db.add_recurring_bill(name, account, category, amount, due_day)
        self.ent_bill_name.delete(0, tk.END)
        self.ent_bill_amt.delete(0, tk.END)
        self.refresh_data()

    def pay_selected_bill(self):
        selected = self.bills_tree.selection()
        if not selected:
            messagebox.showwarning("No Bill Selected", "Select a bill from the list to mark as paid.")
            return

        db_bill_id = selected[0]
        item = self.bills_tree.item(db_bill_id)
        bill_name = item["values"][1]
        status = item["values"][6]

        if "PAID" in status:
            if not messagebox.askyesno("Already Paid", f"'{bill_name}' is already marked PAID for this month. Record another payment anyway?"):
                return

        if self.db.pay_recurring_bill(db_bill_id):
            self.refresh_data()
            messagebox.showinfo("Payment Recorded", f"Paid '{bill_name}' and logged expense to your ledger!")

    def delete_bill(self):
        selected = self.bills_tree.selection()
        if not selected:
            messagebox.showwarning("No Bill Selected", "Select a recurring bill to remove.")
            return

        db_bill_id = selected[0]
        bill_name = self.bills_tree.item(db_bill_id)["values"][1]

        if messagebox.askyesno("Remove Recurring Bill", f"Stop tracking '{bill_name}'?"):
            self.db.delete_recurring_bill(db_bill_id)
            self.refresh_data()

    def update_budget(self):
        try:
            new_budget = float(self.ent_budget.get().strip())
            if new_budget < 0:
                raise ValueError
            self.db.set_budget(new_budget)
            self.refresh_data()
            messagebox.showinfo("Budget Updated", f"Monthly budget set to ₹ {new_budget:,.2f}")
        except ValueError:
            messagebox.showerror("Invalid Budget", "Please enter a valid positive number.")

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"finance_export_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not file_path:
            return

        rows = self.db.get_transactions(
            self.cmb_filter_acc.get(),
            self.cmb_filter_type.get(),
            self.cmb_filter_cat.get()
        )
        with open(file_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Date", "Account", "Type", "Category", "Amount", "Description"])
            for idx, r in enumerate(rows, start=1):
                writer.writerow([idx, r[1], r[2], r[3], r[4], r[5], r[6]])

        messagebox.showinfo("Export Successful", f"Exported {len(rows)} records to:\n{file_path}")

    def refresh_bills_table(self):
        for row in self.bills_tree.get_children():
            self.bills_tree.delete(row)

        today = date.today()
        current_ym = today.strftime("%Y-%m")
        max_day_in_month = calendar.monthrange(today.year, today.month)[1]

        bills = self.db.get_recurring_bills()
        total_monthly = 0.0
        unpaid_total = 0.0
        urgent_count = 0

        for idx, b in enumerate(bills, start=1):
            db_id, name, account, category, amount, due_day, last_paid = b
            total_monthly += amount

            actual_due_day = min(due_day, max_day_in_month)
            due_date_obj = date(today.year, today.month, actual_due_day)
            due_label = due_date_obj.strftime("%d %b %Y")
            days_diff = (due_date_obj - today).days

            if last_paid == current_ym:
                status_text = "✓ PAID"
                tag = "PAID"
            else:
                unpaid_total += amount
                if days_diff < 0:
                    status_text = f"⚠ OVERDUE ({abs(days_diff)}d)"
                    tag = "OVERDUE"
                    urgent_count += 1
                elif days_diff == 0:
                    status_text = "⏰ DUE TODAY"
                    tag = "DUE_SOON"
                    urgent_count += 1
                elif days_diff <= 5:
                    status_text = f"⏳ DUE IN {days_diff}d"
                    tag = "DUE_SOON"
                    urgent_count += 1
                else:
                    status_text = f"UPCOMING ({days_diff}d)"
                    tag = "UPCOMING"

            # iid=str(db_id) stores the true database ID invisibly; idx shows clean 1, 2, 3...
            self.bills_tree.insert(
                "", "end", iid=str(db_id),
                values=(idx, name, account, category, f"₹ {amount:,.2f}", due_label, status_text),
                tags=(tag,)
            )

        self.lbl_bills_summary.config(
            text=f"Monthly Fixed Commitments: ₹ {total_monthly:,.2f}   |   Remaining Unpaid: ₹ {unpaid_total:,.2f}"
        )

        if urgent_count > 0:
            self.lbl_bill_alert.config(
                text=f"🔔 {urgent_count} BILL(S) DUE / OVERDUE",
                bg="#4c0519",
                fg="#fb7185"
            )
        else:
            self.lbl_bill_alert.config(
                text="✓ ALL BILLS ON TRACK",
                bg="#064e3b",
                fg="#34d399"
            )

    def refresh_data(self):
        acc_balances = self.db.get_account_balances()
        bank_bal = acc_balances["Bank"]
        cash_bal = acc_balances["Cash"]
        cc_bal = acc_balances["Credit Card"]

        self.lbl_bank.config(text=f"₹ {bank_bal:,.2f}", fg=self.NEON_CYAN if bank_bal >= 0 else self.NEON_ROSE)
        self.lbl_cash.config(text=f"₹ {cash_bal:,.2f}", fg=self.NEON_MINT if cash_bal >= 0 else self.NEON_ROSE)
        self.lbl_cc.config(text=f"₹ {cc_bal:,.2f}", fg=self.NEON_AMBER if cc_bal >= 0 else self.NEON_ROSE)

        income, expense, balance, month_expense = self.db.get_summary()
        budget = self.db.get_budget()

        self.lbl_balance.config(text=f"₹ {balance:,.2f}", fg="#a78bfa" if balance >= 0 else self.NEON_ROSE)
        self.lbl_budget.config(
            text=f"₹ {month_expense:,.0f} / ₹ {budget:,.0f}",
            fg=self.NEON_ROSE if month_expense > budget else self.NEON_MINT
        )

        for row in self.tree.get_children():
            self.tree.delete(row)

        rows = self.db.get_transactions(
            self.cmb_filter_acc.get(),
            self.cmb_filter_type.get(),
            self.cmb_filter_cat.get()
        )
        for idx, r in enumerate(rows):
            db_id = r[0]
            display_id = idx + 1
            parity = "even" if idx % 2 == 0 else "odd"
            tag = f"{r[3]}_{parity}"
            formatted_row = (display_id, r[1], r[2], r[3], r[4], f"₹ {r[5]:,.2f}", r[6])
            self.tree.insert("", "end", iid=str(db_id), values=formatted_row, tags=(tag,))

        self.refresh_bills_table()
        self.update_charts()


if __name__ == "__main__":
    root = tk.Tk()
    app = FinanceTrackerApp(root)
    root.mainloop()

import streamlit as st
import sqlite3
import calendar
from datetime import datetime, date
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="NOVA FINANCE", page_icon="◆", layout="wide")


class FinanceDatabase:
    def __init__(self, db_name="finance_tracker.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
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

    def add_transaction(self, date_str, account, t_type, category, amount, description):
        self.cursor.execute(
            "INSERT INTO transactions (date, account, type, category, amount, description) VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, account, t_type, category, amount, description)
        )
        self.conn.commit()

    def delete_transaction(self, transaction_id):
        self.cursor.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
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
        self.conn.commit()

    def get_account_balances(self):
        balances = {"Bank": 0.0, "Cash": 0.0, "Credit Card": 0.0}
        self.cursor.execute("""
            SELECT account, SUM(CASE WHEN type = 'Income' THEN amount ELSE -amount END)
            FROM transactions GROUP BY account
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
            SELECT category, SUM(amount) FROM transactions
            WHERE type = 'Expense' GROUP BY category ORDER BY SUM(amount) DESC
        """)
        return self.cursor.fetchall()

    def get_monthly_trends(self):
        self.cursor.execute("""
            SELECT substr(date, 1, 7) AS month,
                   SUM(CASE WHEN type = 'Income' THEN amount ELSE 0 END) AS total_income,
                   SUM(CASE WHEN type = 'Expense' THEN amount ELSE 0 END) AS total_expense
            FROM transactions GROUP BY month ORDER BY month ASC LIMIT 6
        """)
        return self.cursor.fetchall()

    def get_budget(self):
        self.cursor.execute("SELECT value FROM settings WHERE key = 'monthly_budget'")
        res = self.cursor.fetchone()
        return float(res[0]) if res else 50000.0

    def set_budget(self, amount):
        self.cursor.execute("REPLACE INTO settings (key, value) VALUES ('monthly_budget', ?)", (str(amount),))
        self.conn.commit()


db = FinanceDatabase()
ACCOUNTS = ["Bank", "Cash", "Credit Card"]
CATEGORIES = [
    "Salary", "Freelance", "Investments", "Food & Dining",
    "Rent & Utilities", "Subscriptions", "Transport", "Shopping",
    "Healthcare", "Entertainment", "Credit Card Payment", "Savings", "Other"
]

# High-Contrast Dark Fintech Styling (prevents dark text on dark backgrounds)
st.markdown("""
<style>
    .stApp {
        background-color: #0b0f19;
        color: #f8fafc;
    }
    section[data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid #263042;
    }
    section[data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }
    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #111827;
        border: 1px solid #263042;
        border-left: 4px solid #8b5cf6;
        padding: 14px;
        border-radius: 8px;
    }
    div[data-testid="stMetricLabel"] p {
        color: #94a3b8 !important;
        font-weight: 700 !important;
        font-size: 0.8rem !important;
    }
    div[data-testid="stMetricValue"] div {
        color: #f8fafc !important;
        font-weight: 700 !important;
    }
    /* Labels, Headings & Tabs */
    h1, h2, h3, label p, .stMarkdown p {
        color: #f8fafc !important;
    }
    button[data-baseweb="tab"] p {
        color: #cbd5e1 !important;
        font-weight: 600 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #06b6d4 !important;
    }
    /* Buttons */
    div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {
        background-color: #8b5cf6 !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        background-color: #7c3aed !important;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='color:#f8fafc; margin-bottom:0;'>◆ NOVA <span style='color:#8b5cf6;'>FINANCE</span></h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#94a3b8; font-size:0.85rem; letter-spacing:1px;'>PORTFOLIO • CASHFLOW • SUBSCRIPTIONS</p>", unsafe_allow_html=True)

acc_balances = db.get_account_balances()
income, expense, net_worth, month_expense = db.get_summary()
budget = db.get_budget()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("BANK ACCOUNT", f"₹ {acc_balances['Bank']:,.2f}")
c2.metric("CASH WALLET", f"₹ {acc_balances['Cash']:,.2f}")
c3.metric("CREDIT CARD", f"₹ {acc_balances['Credit Card']:,.2f}")
c4.metric("NET WORTH", f"₹ {net_worth:,.2f}")
c5.metric("MONTHLY BUDGET", f"₹ {month_expense:,.0f} / ₹ {budget:,.0f}")

st.divider()

with st.sidebar:
    st.subheader("＋ New Transaction")
    with st.form("tx_form", clear_on_submit=True):
        t_type = st.radio("Flow Type", ["Expense", "Income"], horizontal=True)
        account = st.selectbox("Account", ACCOUNTS)
        t_date = st.date_input("Date", value=date.today())
        category = st.selectbox("Category", CATEGORIES, index=3)
        amount = st.number_input("Amount (₹)", min_value=0.01, step=100.0)
        desc = st.text_input("Note")
        if st.form_submit_button("RECORD TRANSACTION", use_container_width=True):
            db.add_transaction(t_date.strftime("%Y-%m-%d"), account, t_type, category, amount, desc)
            st.rerun()

    st.divider()
    st.subheader("🎯 Monthly Spend Cap")
    new_budget = st.number_input("Budget Limit (₹)", min_value=0.0, value=budget, step=1000.0)
    if st.button("UPDATE BUDGET", use_container_width=True):
        db.set_budget(new_budget)
        st.rerun()

tab_ledger, tab_bills, tab_charts = st.tabs([
    "⚡ TRANSACTIONS LEDGER",
    "🔄 RECURRING BILLS & SUBS",
    "📊 VISUAL ANALYTICS"
])

with tab_ledger:
    f1, f2, f3 = st.columns(3)
    f_acc = f1.selectbox("Filter Account", ["All"] + ACCOUNTS)
    f_type = f2.selectbox("Filter Type", ["All", "Income", "Expense"])
    f_cat = f3.selectbox("Filter Category", ["All"] + CATEGORIES)

    rows = db.get_transactions(f_acc, f_type, f_cat)
    if rows:
        df = pd.DataFrame(rows, columns=["DB_ID", "Date", "Account", "Type", "Category", "Amount", "Description"])
        df.insert(0, "No.", range(1, len(df) + 1))
        st.dataframe(df.drop(columns=["DB_ID"]), use_container_width=True, hide_index=True)

        col_del, col_csv = st.columns([2, 1])
        with col_del:
            del_choice = st.selectbox(
                "Select row to delete",
                options=df["DB_ID"].tolist(),
                format_func=lambda x: f"#{df.loc[df['DB_ID']==x, 'No.'].values[0]} — {df.loc[df['DB_ID']==x, 'Category'].values[0]} (₹{df.loc[df['DB_ID']==x, 'Amount'].values[0]:,.2f})"
            )
            if st.button("DELETE SELECTED"):
                db.delete_transaction(del_choice)
                st.rerun()
        with col_csv:
            st.download_button(
                "EXPORT CSV",
                data=df.drop(columns=["DB_ID"]).to_csv(index=False).encode("utf-8"),
                file_name=f"finance_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("No transactions recorded yet. Add one from the left sidebar.")

with tab_bills:
    with st.form("bill_form", clear_on_submit=True):
        b1, b2, b3, b4, b5 = st.columns([2, 1, 1.5, 1, 1])
        b_name = b1.text_input("Bill Name")
        b_acc = b2.selectbox("Account", ACCOUNTS)
        b_cat = b3.selectbox("Category", CATEGORIES, index=5)
        b_amt = b4.number_input("Amount (₹)", min_value=1.0, step=100.0)
        b_day = b5.number_input("Due Day", min_value=1, max_value=31, value=5)
        if st.form_submit_button("+ ADD BILL"):
            if b_name.strip():
                db.add_recurring_bill(b_name.strip(), b_acc, b_cat, b_amt, int(b_day))
                st.rerun()

    bills = db.get_recurring_bills()
    if bills:
        today = date.today()
        current_ym = today.strftime("%Y-%m")
        max_day = calendar.monthrange(today.year, today.month)[1]
        bill_records = []
        for idx, b in enumerate(bills, start=1):
            db_id, name, account, category, amount, due_day, last_paid = b
            due_obj = date(today.year, today.month, min(due_day, max_day))
            diff = (due_obj - today).days
            if last_paid == current_ym:
                status = "✓ PAID"
            elif diff < 0:
                status = f"⚠ OVERDUE ({abs(diff)}d)"
            elif diff == 0:
                status = "⏰ DUE TODAY"
            else:
                status = f"UPCOMING ({diff}d)"
            bill_records.append({
                "DB_ID": db_id, "No.": idx, "Bill": name, "Account": account,
                "Category": category, "Amount": f"₹ {amount:,.2f}",
                "Due Date": due_obj.strftime("%d %b %Y"), "Status": status
            })

        bdf = pd.DataFrame(bill_records)
        st.dataframe(bdf.drop(columns=["DB_ID"]), use_container_width=True, hide_index=True)

        selected_bill = st.selectbox(
            "Select Bill",
            options=bdf["DB_ID"].tolist(),
            format_func=lambda x: f"{bdf.loc[bdf['DB_ID']==x, 'Bill'].values[0]} ({bdf.loc[bdf['DB_ID']==x, 'Status'].values[0]})"
        )
        p_col, r_col = st.columns(2)
        if p_col.button("✓ PAY SELECTED BILL", use_container_width=True):
            db.pay_recurring_bill(selected_bill)
            st.rerun()
        if r_col.button("REMOVE BILL", use_container_width=True):
            db.delete_recurring_bill(selected_bill)
            st.rerun()
    else:
        st.info("No recurring bills added yet.")

with tab_charts:
    col_pie, col_bar = st.columns(2)
    with col_pie:
        breakdown = db.get_category_breakdown()
        if breakdown:
            fig1, ax1 = plt.subplots(facecolor="#111827")
            ax1.set_facecolor("#111827")
            cats = [r[0] for r in breakdown]
            amts = [r[1] for r in breakdown]
            colors = ["#06b6d4", "#8b5cf6", "#f43f5e", "#10b981", "#f59e0b", "#3b82f6", "#ec4899"]
            wedges, texts, autotexts = ax1.pie(
                amts, labels=cats, autopct="%1.1f%%", startangle=140,
                colors=colors[:len(cats)],
                wedgeprops={"width": 0.44, "edgecolor": "#111827", "linewidth": 2},
                textprops={"color": "#f8fafc", "fontsize": 9, "fontweight": "bold"}
            )
            for at in autotexts:
                at.set_color("#0b0f19")
            ax1.set_title("EXPENSE ALLOCATION", color="#06b6d4", fontweight="bold")
            st.pyplot(fig1)
        else:
            st.info("Add expenses to see category breakdown.")

    with col_bar:
        trends = db.get_monthly_trends()
        if trends:
            fig2, ax2 = plt.subplots(facecolor="#111827")
            ax2.set_facecolor("#111827")
            months = [r[0] for r in trends]
            inc = [r[1] for r in trends]
            exp = [r[2] for r in trends]
            x = range(len(months))
            ax2.bar([i - 0.18 for i in x], inc, width=0.36, label="Income", color="#10b981")
            ax2.bar([i + 0.18 for i in x], exp, width=0.36, label="Expense", color="#f43f5e")
            ax2.set_xticks(list(x))
            ax2.set_xticklabels(months, color="#f8fafc")
            ax2.tick_params(axis="y", colors="#f8fafc")
            for spine in ["top", "right"]:
                ax2.spines[spine].set_visible(False)
            for spine in ["left", "bottom"]:
                ax2.spines[spine].set_color("#334155")
            ax2.set_title("MONTHLY CASHFLOW", color="#8b5cf6", fontweight="bold")
            ax2.legend(facecolor="#1f2937", edgecolor="#334155", labelcolor="#f8fafc")
            st.pyplot(fig2)
        else:
            st.info("Add transactions to see monthly cashflow.")

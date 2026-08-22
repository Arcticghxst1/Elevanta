import os
import re
import sqlite3
from datetime import date
from functools import wraps

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "elevanta-dev-secret")
DB_PATH = os.path.join(app.root_path, "elevanta.db")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)
MODEL = "openrouter/free"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                profit REAL NOT NULL,
                UNIQUE(user_id, entry_date),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )


init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def is_valid_password(password):
    return bool(password) and len(password) >= 9 and re.search(r"\d", password)


def chat_text(messages, max_tokens=4096):
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        "stream": False,
        "timeout": 120,
    }
    completion = client.chat.completions.create(**kwargs)
    message = completion.choices[0].message
    content = (message.content or "").strip()
    if content:
        return content
    reasoning = getattr(message, "reasoning", None) or getattr(
        message, "reasoning_content", None
    )
    if reasoning:
        return str(reasoning).strip()
    return ""


def extract_profit_values(graph_data):
    numbers = re.findall(r"-?\d+(?:\.\d+)?", graph_data)
    return [float(n) for n in numbers]


def profit_is_steadily_decreasing(values, min_points=4, min_drops=3):
    if len(values) < min_points:
        return False

    recent = values[-min_points:]
    drops = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i - 1])
    if drops >= min_drops:
        return True

    midpoint = len(values) // 2
    first_avg = sum(values[:midpoint]) / midpoint
    second_avg = sum(values[midpoint:]) / (len(values) - midpoint)
    falling_overall = second_avg < first_avg * 0.95
    return falling_overall and drops >= min_drops - 1


def declining_profit_advice(business, graph_data):
    return chat_text(
        [
            {
                "role": "user",
                "content": (
                    f"Profit margins for {business} have been steadily decreasing.\n"
                    f"Data:\n{graph_data}\n\n"
                    "Give a short summary of what is going wrong, then list concrete "
                    "ways to raise profit and the specific areas to fix. Keep it practical."
                ),
            }
        ],
        max_tokens=1024,
    )


def format_profit_data(rows):
    return "\n".join(
        f"{row['entry_date']}: ${float(row['profit']):.2f}" for row in rows
    )


def format_monthly_profit_data(rows):
    monthly_totals = {}
    for row in rows:
        month = row["entry_date"][:7]
        monthly_totals[month] = monthly_totals.get(month, 0) + float(row["profit"])
    return "\n".join(
        f"{month}: ${total:.2f}"
        for month, total in sorted(monthly_totals.items())
    )


def profit_chart_svg(rows, width=900, height=360):
    if not rows:
        return ""

    profits = [float(row["profit"]) for row in rows]
    max_v = max(max(profits), 0)
    min_v = min(min(profits), 0)
    span = (max_v - min_v) or 1
    pad_l, pad_r, pad_t, pad_b = 56, 16, 16, 48
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b
    zero_y = pad_t + (max_v / span) * inner_h
    count = len(rows)
    gap = inner_w / count
    bar_w = gap * 0.62
    parts = [
        f'<svg class="profit-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Profit bar chart">'
        f'<line x1="{pad_l}" y1="{zero_y}" x2="{width - pad_r}" y2="{zero_y}" '
        'stroke="#dae4ed" stroke-width="2"/>'
    ]

    for index, row in enumerate(rows):
        value = float(row["profit"])
        bar_h = abs(value) / span * inner_h
        x = pad_l + index * gap + (gap - bar_w) / 2
        if value >= 0:
            y = zero_y - bar_h
            color = "#1f7a4d"
        else:
            y = zero_y
            color = "#c63a3a"
        label = row["entry_date"][5:] if len(row["entry_date"]) >= 10 else row["entry_date"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(bar_h, 1):.1f}" '
            f'fill="{color}" rx="4"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 14}" text-anchor="middle" '
            f'font-size="11" fill="#4a6a80">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def load_profits(user_id, start=None, end=None):
    query = "SELECT entry_date, profit FROM profits WHERE user_id = ?"
    params = [user_id]
    if start:
        query += " AND entry_date >= ?"
        params.append(start)
    if end:
        query += " AND entry_date <= ?"
        params.append(end)
    query += " ORDER BY entry_date"
    with get_db() as conn:
        return conn.execute(query, params).fetchall()


@app.route("/")
@app.route("/login", methods=["GET", "POST"])
@app.route("/login.html", methods=["GET", "POST"])
def login():
    mode = request.args.get("mode", "login")
    error = None
    success = None

    if request.method == "POST":
        mode = request.form.get("mode", "login")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            error = "Please fill in both fields."
        elif not is_valid_email(email):
            error = "Please enter a valid email address."
        elif not is_valid_password(password):
            error = "Password must be at least 9 characters and contain a digit."
        elif mode == "register":
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                        (email, generate_password_hash(password)),
                    )
                success = "Account created. You can sign in now."
                mode = "login"
            except sqlite3.IntegrityError:
                error = "This email is already registered."
        else:
            with get_db() as conn:
                user = conn.execute(
                    "SELECT id, password_hash FROM users WHERE email = ?",
                    (email,),
                ).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                error = "No account found for that email and password. Sign up first."
            else:
                session["user_id"] = user["id"]
                session["email"] = email
                return redirect(url_for("chart"))

    return render_template(
        "login.html",
        mode=mode,
        error=error,
        success=success,
    )


@app.route("/register", methods=["GET", "POST"])
@app.route("/register.html", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return redirect(url_for("login", mode="register"))
    return login()


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/home")
@app.route("/home.html")
def home():
    return send_from_directory(os.path.join(app.root_path, "main"), "home.html")


@app.route("/index")
@app.route("/index.html")
@login_required
def dashboard():
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    today_value = today.isoformat()
    month_rows = load_profits(session["user_id"], month_start, today_value)
    all_rows = load_profits(session["user_id"])
    month_profit = sum(float(row["profit"]) for row in month_rows)
    total_profit = sum(float(row["profit"]) for row in all_rows)
    trend_alert = profit_is_steadily_decreasing(
        [float(row["profit"]) for row in all_rows]
    )

    if len(month_rows) >= 2:
        first_profit = float(month_rows[0]["profit"])
        last_profit = float(month_rows[-1]["profit"])
        growth = ((last_profit - first_profit) / abs(first_profit) * 100) if first_profit else 0
    else:
        growth = 0

    return render_template(
        "index.html",
        active_page="dashboard",
        username=session.get("email", "").split("@")[0],
        month_profit=month_profit,
        total_profit=total_profit,
        growth=growth,
        alerts=1 if trend_alert else 0,
        has_data=bool(all_rows),
    )


@app.route("/chart", methods=["GET", "POST"])
@app.route("/chart.html", methods=["GET", "POST"])
@app.route("/new.html", methods=["GET", "POST"])
@login_required
def chart():
    save_status = "Ready to save weekly profit data"
    save_kind = "info"
    today = date.today().isoformat()
    start = request.values.get("start") or today[:8] + "01"
    end = request.values.get("end") or today
    entry_date = request.values.get("date") or today
    profit_value = request.values.get("profit", "")
    range_error = ""

    if request.method == "POST" and request.form.get("action") == "save":
        entry_date = request.form.get("date", "").strip()
        profit_raw = request.form.get("profit", "").strip()
        if not entry_date:
            save_status = "Please select a date."
            save_kind = "danger"
        elif profit_raw == "":
            save_status = "Please enter a profit amount."
            save_kind = "danger"
        else:
            try:
                profit_num = float(profit_raw)
            except ValueError:
                save_status = "Please enter a valid number for profit."
                save_kind = "danger"
            else:
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM profits WHERE user_id = ? AND entry_date = ?",
                        (session["user_id"], entry_date),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE profits SET profit = ? WHERE id = ?",
                            (profit_num, existing["id"]),
                        )
                        save_status = f"Updated profit for {entry_date} to ${profit_num:.2f}"
                        save_kind = "warning"
                    else:
                        conn.execute(
                            "INSERT INTO profits (user_id, entry_date, profit) VALUES (?, ?, ?)",
                            (session["user_id"], entry_date, profit_num),
                        )
                        save_status = f"Saved profit ${profit_num:.2f} for {entry_date}"
                        save_kind = "success"
                profit_value = ""

    if start and end and end < start:
        range_error = "End date must be after start date."
        rows = []
        chart_status = "Please fix the date range."
        chart_kind = "warning"
        chart_svg = ""
    else:
        rows = load_profits(session["user_id"], start, end)
        chart_svg = profit_chart_svg(rows)
        if not rows:
            all_rows = load_profits(session["user_id"])
            if not all_rows:
                chart_status = "No profit data saved yet."
                save_status = save_status if save_kind != "info" else "No data saved yet. Add your first profit record!"
            else:
                chart_status = "No records found in the selected date range."
            chart_kind = "info"
        else:
            chart_status = (
                f"Showing {len(rows)} record{'s' if len(rows) != 1 else ''} "
                f"from {rows[0]['entry_date']} to {rows[-1]['entry_date']}."
            )
            chart_kind = "success"

    return render_template(
        "chart.html",
        active_page="chart",
        save_status=save_status,
        save_kind=save_kind,
        chart_status=chart_status,
        chart_kind=chart_kind,
        range_error=range_error,
        entry_date=entry_date,
        profit_value=profit_value,
        start=start,
        end=end,
        chart_svg=chart_svg,
    )


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/ask", methods=["GET", "POST"])
@app.route("/ask.html", methods=["GET", "POST"])
@login_required
def ask():
    answer = None
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            try:
                answer = chat_text(
                    [{"role": "user", "content": question}],
                    max_tokens=2048,
                )
            except Exception as e:
                answer = f"Error generating answer: {e}"

    return render_template(
        "ask.html",
        answer=answer,
        question=request.form.get("question", ""),
        active_page="ask",
    )


@app.route("/graph", methods=["GET", "POST"])
@app.route("/graph-summary", methods=["GET", "POST"])
@app.route("/graph.html", methods=["GET", "POST"])
@login_required
def graphSummary():
    answer = None
    alert = False
    business = ""
    saved_rows = load_profits(session["user_id"])
    graph_data = format_profit_data(saved_rows)

    if request.method == "POST":
        business = request.form.get("business", "").strip() or "the business"
        if graph_data:
            values = extract_profit_values(graph_data)
            alert = profit_is_steadily_decreasing(values)
            if alert:
                try:
                    answer = declining_profit_advice(business, graph_data)
                except Exception as e:
                    answer = f"Error generating answer: {e}"

    return render_template(
        "graph.html",
        answer=answer,
        alert=alert,
        business=business,
        graph_data=graph_data,
        saved_count=len(saved_rows),
        active_page="graph",
    )

@app.route("/see-solutions", methods=["GET", "POST"])
@login_required
def seeSolution():
    answer = None
    alert = False
    business = session.get("email", "")
    graph_data = ""

    rows = load_profits(session["user_id"])

    if not rows:
        answer = "No profit data available. Please add profit records first."
    else:
        float_values = [float(row["profit"]) for row in rows]

        alert = profit_is_steadily_decreasing(float_values)

    if alert:
        graph_data = "\n".join(f"{row['entry_date']}: {row['profit']}" for row in rows)

        try:
            answer = chat_text(
                [
                    {
                        "role": "user",
                        "content": (
                            f"Here is the profit data for {business}: {graph_data}. "
                            "Based on this information, suggest projects the business could do to improve their financial performance."
                        ),
                    },
                ],
                max_tokens=2048,
            )

        except Exception as e:
            answer = f"Error generating answer: {e}"
    elif rows:
        answer = "Profit data is not steadily decreasing. No specific solutions suggested."

    return render_template(
        "see-solutions.html",
        answer=answer,
        business=business,
        graph_data=graph_data,
        active_page="see-solutions",
    )


@app.route("/ideas", methods=["GET", "POST"])
@app.route("/ideas.html", methods=["GET", "POST"])
@login_required
def projectIdea():
    answer = None
    business = ""
    saved_rows = load_profits(session["user_id"])
    graph_data = format_monthly_profit_data(saved_rows)
    if request.method == "POST":
        business = request.form.get("business", "").strip()
        if business and graph_data:
            try:
                answer = chat_text(
                    [
                        {
                            "role": "user",
                            "content": (
                                f"The business is {business}. Review its monthly income "
                                f"from the chart data below:\n{graph_data}\n\n"
                                "Suggest practical project ideas based on its monthly income. "
                                "Explain why each idea fits the business and income pattern, "
                                "and prioritize ideas that are realistic for its current scale."
                            ),
                        }
                    ],
                    max_tokens=1024,
                )
            except Exception as e:
                answer = f"Error generating answer: {e}"
        elif not business:
            answer = "Please enter a business name."
        else:
            answer = "No saved chart data is available yet. Add profit records first."

    return render_template(
        "ideas.html",
        answer=answer,
        business=business,
        saved_count=len(saved_rows),
        active_page="ideas",
    )



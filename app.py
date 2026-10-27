
import sqlite3
from pathlib import Path
from datetime import datetime

import streamlit as st

DB = Path(__file__).parent / "waste_planner.db"

st.set_page_config(
    page_title="EcoRoute | Smart Waste Planner",
    page_icon="♻️",
    layout="wide",
)

# ---------- DATABASE ----------

def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                area TEXT NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                fill INTEGER NOT NULL,
                last_collected TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bin_id INTEGER NOT NULL,
                area TEXT NOT NULL,
                fill_before INTEGER NOT NULL,
                collected_at TEXT NOT NULL
            )
        """)

        if conn.execute("SELECT COUNT(*) FROM bins").fetchone()[0] == 0:
            samples = [
                ("Central Market", 1, 1, 96, 3),
                ("Central Market", 2, 1, 78, 2),
                ("Bus Station", 4, 1, 91, 4),
                ("Bus Station", 5, 2, 43, 1),
                ("Residential Zone A", 1, 3, 65, 2),
                ("Residential Zone A", 2, 4, 88, 3),
                ("Residential Zone B", 5, 4, 32, 1),
                ("Residential Zone B", 6, 3, 73, 2),
                ("Tech Park", 7, 1, 84, 3),
                ("Tech Park", 8, 2, 51, 1),
                ("Hospital Road", 7, 5, 97, 4),
                ("Hospital Road", 8, 5, 60, 2),
                ("College Area", 3, 6, 28, 1),
                ("College Area", 4, 7, 81, 3),
                ("Park Avenue", 6, 7, 46, 2),
                ("Park Avenue", 8, 7, 90, 4),
            ]
            now = datetime.now()
            for area, x, y, fill, days in samples:
                last = (now.timestamp() - days * 86400)
                last_text = datetime.fromtimestamp(last).isoformat(
                    timespec="seconds"
                )
                conn.execute("""
                    INSERT INTO bins
                    (area, x, y, fill, last_collected)
                    VALUES (?, ?, ?, ?, ?)
                """, (area, x, y, fill, last_text))


def get_bins():
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM bins ORDER BY id"
        ).fetchall()]


def get_history():
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM collections ORDER BY id DESC LIMIT 100"
        ).fetchall()]


def days_waiting(b):
    try:
        previous = datetime.fromisoformat(b["last_collected"])
        return max(0, (datetime.now() - previous).total_seconds() / 86400)
    except (ValueError, TypeError):
        return 0


def priority(b):
    # Explainable heuristic score, not a trained ML prediction.
    fill = b["fill"]
    age = days_waiting(b)
    overflow = max(0, fill - 70) / 30 * 25
    age_score = min(age / 4, 1) * 15
    return round(fill * 0.60 + overflow + age_score, 1)


def distance(a, b):
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def make_route(candidates, depot):
    # Greedy nearest-neighbour route heuristic.
    remaining = list(candidates)
    current = depot
    route = []

    while remaining:
        chosen = min(
            remaining,
            key=lambda b: (
                distance(current, b),
                -priority(b)
            )
        )
        route.append(chosen)
        remaining.remove(chosen)
        current = chosen

    return route


def complete_collection(route):
    stamp = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        for b in route:
            current = conn.execute(
                "SELECT * FROM bins WHERE id = ?",
                (b["id"],)
            ).fetchone()
            if current is None:
                continue

            conn.execute("""
                INSERT INTO collections
                (bin_id, area, fill_before, collected_at)
                VALUES (?, ?, ?, ?)
            """, (
                current["id"], current["area"],
                current["fill"], stamp
            ))

            conn.execute("""
                UPDATE bins
                SET fill = 0, last_collected = ?
                WHERE id = ?
            """, (stamp, current["id"]))


initialize()

# ---------- STYLE ----------

st.markdown("""
<style>
.stApp { background: #f4f7f2; }
h1, h2, h3 { color: #174b32; }
div[data-testid="stMetric"] {
    background: white;
    border: 1px solid #dce7dc;
    padding: 15px;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

st.title("♻️ EcoRoute")
st.subheader("AI-Based Smart Waste Collection Planner")
st.caption(
    "Smart bin monitoring • Priority scoring • Collection route planning"
)

bins = get_bins()
history = get_history()

# ---------- CONTROLS ----------

with st.sidebar:
    st.header("Route Settings")
    threshold = st.slider("Collection threshold (%)", 30, 95, 75)
    max_stops = st.slider(
        "Maximum route stops", 1, max(1, len(bins)), min(6, len(bins))
    )
    depot_x = st.number_input("Depot X", 0, 10, 0)
    depot_y = st.number_input("Depot Y", 0, 10, 0)
    st.info(
        "Demo uses simulated sensor readings. The heuristic is a "
        "decision-support algorithm, not a trained machine-learning model."
    )

# ---------- DASHBOARD ----------

urgent = [b for b in bins if b["fill"] >= threshold]
average = sum(b["fill"] for b in bins) / max(1, len(bins))
overflow = sum(b["fill"] >= 90 for b in bins)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total bins", len(bins))
m2.metric("Need collection", len(urgent))
m3.metric("Average fill", f"{average:.1f}%")
m4.metric("Overflow risk", overflow)

st.divider()

dashboard, routes_tab, manage_tab, history_tab = st.tabs([
    "📊 Dashboard",
    "🗺️ Route Planner",
    "🛠️ Manage Bins",
    "📋 Collection History",
])

with dashboard:
    st.markdown("### Bin Monitoring")
    for b in sorted(bins, key=priority, reverse=True):
        if b["fill"] >= 90:
            status = "🔴 URGENT"
        elif b["fill"] >= threshold:
            status = "🟠 COLLECT SOON"
        else:
            status = "🟢 NORMAL"

        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 3, 2])
            c1.markdown(f"**WB-{b['id']:03d}**")
            c1.caption(b["area"])
            c2.progress(int(b["fill"]))
            c2.caption(f"Fill level: {b['fill']}%")
            c3.write(status)
            c3.caption(f"Priority: {priority(b)}")

    st.markdown("### Highest-Priority Bins")
    ranked = sorted(bins, key=priority, reverse=True)[:5]
    st.dataframe([
        {
            "Bin": f"WB-{b['id']:03d}",
            "Area": b["area"],
            "Fill (%)": b["fill"],
            "Days waiting": round(days_waiting(b), 1),
            "Priority score": priority(b),
        }
        for b in ranked
    ], use_container_width=True, hide_index=True)

with routes_tab:
    st.markdown("### Generate Collection Route")

    candidates = sorted(
        [b for b in bins if b["fill"] >= threshold],
        key=priority,
        reverse=True
    )[:max_stops]

    if not candidates:
        st.success("No bins currently meet the collection threshold.")
    else:
        depot = {"x": int(depot_x), "y": int(depot_y)}
        route = make_route(candidates, depot)

        current = depot
        total_distance = 0
        route_rows = []

        for i, b in enumerate(route, start=1):
            leg = distance(current, b)
            total_distance += leg
            route_rows.append({
                "Stop": i,
                "Bin": f"WB-{b['id']:03d}",
                "Area": b["area"],
                "Fill (%)": b["fill"],
                "Priority": priority(b),
                "Leg distance": leg,
            })
            current = b

        total_distance += distance(current, depot)

        c1, c2, c3 = st.columns(3)
        c1.metric("Planned stops", len(route))
        c2.metric("Grid distance", total_distance)
        c3.metric("Critical bins", sum(b["fill"] >= 90 for b in route))

        st.dataframe(
            route_rows, use_container_width=True, hide_index=True
        )
        st.write(
            "Route: Depot → "
            + " → ".join(f"WB-{b['id']:03d}" for b in route)
            + " → Depot"
        )
        st.caption(
            "Uses a greedy nearest-neighbour heuristic. Distances are "
            "simplified grid units, not real-world kilometres."
        )

        if st.button("✅ Complete this collection route", type="primary"):
            complete_collection(route)
            st.success(f"Collection recorded for {len(route)} bins.")
            st.rerun()

with manage_tab:
    st.markdown("### Update Simulated Sensor Reading")
    options = {
        f"WB-{b['id']:03d} — {b['area']}": b["id"]
        for b in bins
    }

    with st.form("update_form"):
        selected_label = st.selectbox("Select bin", list(options.keys()))
        selected_id = options[selected_label]
        selected_bin = next(b for b in bins if b["id"] == selected_id)
        new_fill = st.slider(
            "Fill level (%)", 0, 100, int(selected_bin["fill"])
        )
        update = st.form_submit_button("Save reading")

    if update:
        with db() as conn:
            conn.execute(
                "UPDATE bins SET fill = ? WHERE id = ?",
                (new_fill, selected_id)
            )
        st.success("Bin reading updated.")
        st.rerun()

    st.divider()
    st.markdown("### Register New Bin")

    with st.form("add_form", clear_on_submit=True):
        area = st.text_input("Area name")
        x_col, y_col = st.columns(2)
        x = x_col.number_input("Grid X", 0, 10, 1, key="add_x")
        y = y_col.number_input("Grid Y", 0, 10, 1, key="add_y")
        fill = st.slider("Initial fill (%)", 0, 100, 20, key="add_fill")
        add = st.form_submit_button("Add bin")

    if add:
        if not area.strip():
            st.error("Please enter an area name.")
        else:
            now = datetime.now().isoformat(timespec="seconds")
            with db() as conn:
                conn.execute("""
                    INSERT INTO bins
                    (area, x, y, fill, last_collected)
                    VALUES (?, ?, ?, ?, ?)
                """, (area.strip(), int(x), int(y), fill, now))
            st.success("New bin registered.")
            st.rerun()

    st.markdown("### All Registered Bins")
    st.dataframe([
        {
            "ID": f"WB-{b['id']:03d}",
            "Area": b["area"],
            "X": b["x"],
            "Y": b["y"],
            "Fill (%)": b["fill"],
        }
        for b in bins
    ], use_container_width=True, hide_index=True)

with history_tab:
    st.markdown("### Recent Collection History")
    if history:
        st.dataframe([
            {
                "Bin": f"WB-{r['bin_id']:03d}",
                "Area": r["area"],
                "Fill before collection (%)": r["fill_before"],
                "Collected at": r["collected_at"],
            }
            for r in history
        ], use_container_width=True, hide_index=True)
    else:
        st.info("No collection records yet. Complete a route to create history.")

st.divider()
st.caption("EcoRoute prototype • Simulated data • SQLite • Heuristic route planning")

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import re

MANUFACTURER_FILES = {
    "Fujitsu": "fujitsu_capacities_calculated.xlsx",
    "LG": "lg_capacities_calculated.xlsx",
}

SHEET_NAME = "indoor_combinations"  # set this to your actual sheet name (same for both files)

UNIT_COLS = [f"Unit {i}" for i in range(1, 9)]
CAP_COLS  = [f"Max Capacity Unit {i}" for i in range(1, 9)]

BASE_REQUIRED = {"Model", "Type", "Indoor Capacity", "Total Capacity"} | set(UNIT_COLS) | set(CAP_COLS)

def detect_unit_columns(df: pd.DataFrame):
    # Find Unit 1..N and Max Capacity Unit 1..N that actually exist
    unit_nums = []
    for c in df.columns:
        m = re.fullmatch(r"Unit (\d+)", str(c).strip())
        if m:
            unit_nums.append(int(m.group(1)))

    if not unit_nums:
        raise ValueError("No 'Unit N' columns found.")

    max_n = max(unit_nums)

    unit_cols = [f"Unit {i}" for i in range(1, max_n + 1) if f"Unit {i}" in df.columns]
    cap_cols  = [f"Max Capacity Unit {i}" for i in range(1, max_n + 1) if f"Max Capacity Unit {i}" in df.columns]

    # Ensure paired columns exist (Unit i and Max Capacity Unit i)
    paired = []
    for i in range(1, max_n + 1):
        u = f"Unit {i}"
        c = f"Max Capacity Unit {i}"
        if u in df.columns and c in df.columns:
            paired.append((u, c))

    if not paired:
        raise ValueError("Found Unit columns but no matching Max Capacity Unit columns.")

    unit_cols = [u for u, _ in paired]
    cap_cols  = [c for _, c in paired]
    return unit_cols, cap_cols

def load_combos(manufacturer: str) -> pd.DataFrame:
    path = MANUFACTURER_FILES[manufacturer]
    df = pd.read_excel(path, sheet_name=SHEET_NAME)

    # Detect unit/cap columns dynamically (6 for Fujitsu, 8 for LG)
    unit_cols, cap_cols = detect_unit_columns(df)

    required = {"Model", "Type", "Indoor Capacity", "Total Capacity"} | set(unit_cols) | set(cap_cols)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {path} sheet '{SHEET_NAME}': {sorted(missing)}")

    df = df.copy()
    df.attrs["UNIT_COLS"] = unit_cols
    df.attrs["CAP_COLS"] = cap_cols

    # normalize + numeric conversions
    df["Model"] = df["Model"].astype(str).str.strip()
    df["Type"] = df["Type"].fillna("").astype(str).str.strip()
    df["Indoor Capacity"] = pd.to_numeric(df["Indoor Capacity"], errors="coerce")
    df["Total Capacity"] = pd.to_numeric(df["Total Capacity"], errors="coerce")

    for c in unit_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in cap_cols:
        df[c] = df[c].astype(str).str.replace(",", "", regex=False).replace({"nan": None, "None": None})
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

def row_heads_and_caps(row, unit_cols, cap_cols):
    sizes, caps = [], []
    for ucol, ccol in zip(unit_cols, cap_cols):
        u = row.get(ucol)
        c = row.get(ccol)
        if pd.notna(u) and pd.notna(c):
            sizes.append(int(u))
            caps.append(float(c))
    return sizes, caps

def can_cover_requirements(caps, reqs):
    """Feasibility check: assign largest caps to largest reqs (greedy)."""
    caps_sorted = sorted(caps, reverse=True)
    reqs_sorted = sorted(reqs, reverse=True)
    if len(caps_sorted) < len(reqs_sorted):
        return False, None

    # If you want EXACT head-count match, caller should filter before this.
    for cap, req in zip(caps_sorted, reqs_sorted):
        if cap < req:
            return False, None

    # Build a simple mapping (sorted-to-sorted)
    mapping = list(zip(reqs_sorted, caps_sorted))
    return True, mapping

def find_options(df: pd.DataFrame, reqs, type_filter="All", max_results=300):
    """
    Find matching combo rows for the given head/room requirements.

    Rules (current version):
      - No limits beyond what's in the row (i.e., we require EXACT head count match)
      - A row matches if its available head capacities can cover the requirements
        (largest cap covers largest req, etc.)
      - Uses df.attrs["UNIT_COLS"] and df.attrs["CAP_COLS"] detected at load time
    """
    if "UNIT_COLS" not in df.attrs or "CAP_COLS" not in df.attrs:
        raise ValueError(
            "df is missing UNIT/CAP column metadata. "
            "Make sure load_combos() sets df.attrs['UNIT_COLS'] and df.attrs['CAP_COLS']."
        )

    unit_cols = df.attrs["UNIT_COLS"]
    cap_cols  = df.attrs["CAP_COLS"]

    reqs = [float(x) for x in reqs]
    n = len(reqs)

    # Optional filter by Type
    if type_filter != "All":
        df2 = df[df["Type"].fillna("").astype(str).str.strip() == type_filter].copy()
    else:
        df2 = df.copy()

    results = []

    for _, row in df2.iterrows():
        # Extract heads + capacities from this row using the detected columns
        sizes = []
        caps = []
        for ucol, ccol in zip(unit_cols, cap_cols):
            u = row.get(ucol)
            c = row.get(ccol)
            if pd.notna(u) and pd.notna(c):
                sizes.append(int(u))
                caps.append(float(c))

        # Require exact number of heads == number of requirements
        if len(caps) != n:
            continue

        # Feasibility check: sort descending and compare
        caps_sorted = sorted(caps, reverse=True)
        reqs_sorted = sorted(reqs, reverse=True)

        ok = True
        mapping = []
        for req, cap in zip(reqs_sorted, caps_sorted):
            if cap < req:
                ok = False
                break
            mapping.append((req, cap))

        if not ok:
            continue

        worst_margin = min(cap - req for req, cap in mapping)
        total_margin = sum(caps_sorted) - sum(reqs_sorted)

        combo_units = "+".join(map(str, sizes))
        combo_caps  = "+".join(f"{c:.0f}" for c in caps)

        results.append({
            "Model": row["Model"],
            "Type": row["Type"],
            "Indoor Capacity": row["Indoor Capacity"],
            "Total Capacity": row["Total Capacity"],
            "Units": combo_units,
            "Caps": combo_caps,
            "worst_margin": worst_margin,
            "margin_total": total_margin,
            "mapping": mapping,  # list of (req, cap) after sorting
        })

        if len(results) >= max_results:
            break

    # Rank: tighter fits first (still >=0), then smaller total oversize
    results.sort(key=lambda r: (-r["worst_margin"], r["margin_total"]))
    return results

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ASHP Combo Finder (dynamic 6 vs 8 heads)")
        self.geometry("1200x700")

        self.df_cache = {}
        self.last_results = []

        # ---------- TOP BAR ----------
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Manufacturer").grid(row=0, column=0, sticky="w")
        self.manufacturer = tk.StringVar(value="Fujitsu")
        self.manufacturer_combo = ttk.Combobox(
            top,
            textvariable=self.manufacturer,
            values=list(MANUFACTURER_FILES.keys()),
            width=12,
            state="readonly",
        )
        self.manufacturer_combo.grid(row=0, column=1, padx=6)

        ttk.Button(top, text="Load / Refresh", command=self.load_data).grid(row=0, column=2, padx=10)

        ttk.Label(top, text="Type").grid(row=0, column=3, sticky="w")
        self.type_filter = tk.StringVar(value="All")
        self.type_combo = ttk.Combobox(top, textvariable=self.type_filter, values=["All"], width=18, state="readonly")
        self.type_combo.grid(row=0, column=4, padx=6)

        ttk.Label(top, text="Heads / Rooms").grid(row=0, column=5, sticky="w")
        self.room_count = tk.IntVar(value=2)

        # IMPORTANT: store the spinbox as self.room_spin so we can update `to=...` dynamically.
        self.room_spin = ttk.Spinbox(
            top,
            from_=1,
            to=8,  # will be overwritten after load based on detected columns (6 or 8)
            textvariable=self.room_count,
            width=5,
            command=self.render_room_inputs,
        )
        self.room_spin.grid(row=0, column=6, padx=6)

        ttk.Button(top, text="Find Options", command=self.run_solver).grid(row=0, column=7, padx=10)

        # ---------- ROOM INPUTS ----------
        self.rooms_frame = ttk.LabelFrame(self, text="Room/Head BTU Requirements", padding=10)
        self.rooms_frame.pack(fill="x", padx=10, pady=8)

        self.room_entries = []
        self.render_room_inputs()

        # ---------- RESULTS TABLE ----------
        results_frame = ttk.Frame(self, padding=10)
        results_frame.pack(fill="both", expand=True)

        cols = ("Model", "Type", "Indoor Capacity", "Total Capacity", "Units", "worst_margin", "margin_total")
        self.tree = ttk.Treeview(results_frame, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
            width = 180
            if c in ("worst_margin", "margin_total"):
                width = 120
            if c == "Units":
                width = 240
            self.tree.column(c, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(fill="y", side="right")

        # ---------- DETAILS BOX ----------
        self.details = tk.Text(self, height=9)
        self.details.pack(fill="both", expand=False, padx=10, pady=8)
        #self.details.pack(fill="x", padx=10, pady=8)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Load initial data
        self.load_data()

    def render_room_inputs(self):
        """Rebuild the requirement inputs when head count changes."""
        for w in self.rooms_frame.winfo_children():
            w.destroy()
        self.room_entries.clear()

        n = int(self.room_count.get())
        for i in range(n):
            ttk.Label(self.rooms_frame, text=f"Req {i+1}").grid(
                row=i // 4, column=(i % 4) * 2, sticky="w", padx=(0, 6), pady=3
            )
            e = ttk.Entry(self.rooms_frame, width=12)
            e.grid(row=i // 4, column=(i % 4) * 2 + 1, sticky="w", padx=(0, 18), pady=3)

            # example default values
            e.insert(0, "9000" if i == 0 else "7000")
            self.room_entries.append(e)

    def load_data(self):
        """Load manufacturer file, detect max heads (6 vs 8), update UI."""
        m = self.manufacturer.get()
        try:
            df = load_combos(m)  # <-- your function that sets df.attrs["UNIT_COLS"]/["CAP_COLS"]
            self.df_cache[m] = df

            # Update Type dropdown (All + unique Type values)
            types = sorted(set(df["Type"].fillna("").astype(str).str.strip()))
            self.type_combo.configure(values=["All"] + types)
            self.type_filter.set("All")

            # Detect max heads from the actual columns in the workbook
            if "UNIT_COLS" not in df.attrs:
                raise ValueError("load_combos() did not set df.attrs['UNIT_COLS'].")
            max_heads = len(df.attrs["UNIT_COLS"])

            # Update spinbox maximum (6 for Fujitsu, 8 for LG, etc.)
            self.room_spin.configure(to=max_heads)

            # Clamp current value if it exceeds manufacturer max
            if self.room_count.get() > max_heads:
                self.room_count.set(max_heads)
                self.render_room_inputs()

            messagebox.showinfo("Loaded", f"Loaded {len(df)} rows for {m}. Max heads detected: {max_heads}")

        except Exception as ex:
            messagebox.showerror("Load error", str(ex))

    def run_solver(self):
        """Run the match finder and populate results."""
        m = self.manufacturer.get()
        if m not in self.df_cache:
            self.load_data()
            if m not in self.df_cache:
                return

        try:
            reqs = [float(e.get().strip()) for e in self.room_entries]
        except Exception:
            messagebox.showerror("Input error", "All requirements must be numeric.")
            return

        df = self.df_cache[m]
        type_filter = self.type_filter.get()

        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", "end")

        self.last_results = find_options(df, reqs=reqs, type_filter=type_filter, max_results=300)

        if not self.last_results:
            messagebox.showinfo("No matches", "No rows found that can cover these requirements with the same head count.")
            return

        for r in self.last_results:
            self.tree.insert(
                "",
                "end",
                values=(
                    r["Model"],
                    r["Type"],
                    "" if pd.isna(r["Indoor Capacity"]) else int(r["Indoor Capacity"]),
                    "" if pd.isna(r["Total Capacity"]) else int(r["Total Capacity"]),
                    r["Units"],
                    f"{r['worst_margin']:.0f}",
                    f"{r['margin_total']:.0f}",
                ),
            )

    def on_select(self, _evt):
        DETAILS_MIN_LINES = 6
        DETAILS_MAX_LINES = 20  # keep it from taking over the whole window

        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        r = self.last_results[idx]

        lines = []
        lines.append(f"Model: {r['Model']}")
        lines.append(f"Type: {r['Type']}")
        lines.append(f"Units: {r['Units']}")
        lines.append(f"Indoor Capacity: {r['Indoor Capacity']} | Total Capacity: {r['Total Capacity']}")
        lines.append("")
        lines.append("Assignment (sorted req -> sorted cap):")
        for i, (req, cap) in enumerate(r["mapping"], start=1):
            lines.append(f"  {i}. req={req:.0f}  <=  cap={cap:.0f}   (margin {cap-req:.0f})")
        lines.append("")
        lines.append(f"Worst margin: {r['worst_margin']:.0f}")
        lines.append(f"Total oversize: {r['margin_total']:.0f}")

        text = "\n".join(lines)

        # --- AUTO-FIT HEIGHT ---
        line_count = text.count("\n") + 1
        new_height = max(DETAILS_MIN_LINES, min(DETAILS_MAX_LINES, line_count))
        self.details.configure(height=new_height)

        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)

if __name__ == "__main__":
    App().mainloop()
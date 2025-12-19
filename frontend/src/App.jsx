import { useEffect, useMemo, useState } from "react";

const MANUFACTURERS = ["Fujitsu", "LG"];

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function toNumberOrNull(v) {
  const x = Number(String(v).trim());
  return Number.isFinite(x) ? x : null;
}

export default function App() {
  // --- top bar state ---
  const [manufacturer, setManufacturer] = useState("Fujitsu");
  const [typeFilter, setTypeFilter] = useState("All");
  const [types, setTypes] = useState(["All"]);

  const [maxHeads, setMaxHeads] = useState(8);
  const [roomCount, setRoomCount] = useState(2);

  // --- dynamic room requirements ---
  const [reqs, setReqs] = useState(["9000", "7000"]); // same default vibe as your GUI

  // --- results ---
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedRow, setSelectedRow] = useState(null);
  const [error, setError] = useState("");

  // details autosize like your Tkinter Text box
  const detailsText = useMemo(() => {
    if (!selectedRow) return "";

    const r = selectedRow;
    const model = r.Model ?? "";
    const type = r.Type ?? "";
    const units = r.Units ?? "";
    const indoorCap = r["Indoor Capacity"] ?? "";
    const totalCap = r["Total Capacity"] ?? "";
    const mapping = Array.isArray(r.mapping) ? r.mapping : [];

    const lines = [
      `Model: ${model}`,
      `Type: ${type}`,
      `Units: ${units}`,
      `Indoor Capacity: ${indoorCap} | Total Capacity: ${totalCap}`,
      "",
      "Assignment (sorted req -> sorted cap):",
    ];

    if (mapping.length) {
      mapping.forEach(([req, cap], i) => {
        lines.push(
          `  ${i + 1}. req=${Number(req).toFixed(0)} <= cap=${Number(cap).toFixed(0)} (margin ${(Number(cap) - Number(req)).toFixed(0)})`
        );
      });
    } else {
      lines.push("  (no mapping returned)");
    }

    lines.push("");
    lines.push(`Worst margin: ${Number(r.worst_margin ?? 0).toFixed(0)}`);
    lines.push(`Total oversize: ${Number(r.margin_total ?? 0).toFixed(0)}`);

    return lines.join("\n");
  }, [selectedRow]);

  const detailsRows = useMemo(() => {
    const min = 6;
    const max = 20;
    const lineCount = detailsText ? detailsText.split("\n").length : min;
    return Math.max(min, Math.min(max, lineCount));
  }, [detailsText]);

  // keep reqs array in sync with roomCount
  useEffect(() => {
    setReqs((prev) => {
      const next = prev.slice(0, roomCount);
      while (next.length < roomCount) next.push(next.length === 0 ? "9000" : "7000");
      return next;
    });
    setSelectedRow(null);
  }, [roomCount]);

  // --- load/refresh meta like your load_data() ---
  async function loadData(m = manufacturer) {
    setError("");
    setLoading(true);
    setResults([]);
    setSelectedRow(null);

    try {
      const res = await fetch(`/api/meta?manufacturer=${encodeURIComponent(m)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to load metadata");

      setTypes(data.types || ["All"]);
      setTypeFilter("All");

      const mh = Number(data.max_heads || 8);
      setMaxHeads(mh);

      // clamp roomCount to manufacturer max heads (like your GUI)
      setRoomCount((rc) => clamp(rc, 1, mh));
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // load once on mount (initial manufacturer)
  useEffect(() => {
    loadData(manufacturer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // when manufacturer changes, auto refresh meta (matches your UX)
  useEffect(() => {
    loadData(manufacturer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manufacturer]);

  async function runSolver() {
    setError("");
    setLoading(true);
    setResults([]);
    setSelectedRow(null);

    // validate reqs numeric
    const parsed = reqs.map(toNumberOrNull);
    if (parsed.some((x) => x == null)) {
      setLoading(false);
      setError("All requirements must be numeric.");
      return;
    }

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manufacturer,
          reqs: parsed,
          type_filter: typeFilter,
          max_results: 300,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Run failed");

      const list = data?.result?.results || [];
      setResults(list);

      if (list.length === 0) {
        setError("No rows found that can cover these requirements with the same head count.");
      } else {
        const first = [...list].sort(
          (a, b) => Number(a.margin_total ?? 0) - Number(b.margin_total ?? 0)
        )[0];
        setSelectedRow(first ?? null);
      }

    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // Organizing list of models in order based on total oversize
  // sort results by Total Oversize (margin_total) smallest -> largest
  const sortedResults = useMemo(() => {
    return [...results]
      .map((r, idx) => ({
        ...r,
        _rowId: `${r.Model}-${r.Type}-${r.Units}-${idx}`, // stable identity
        _oversizeNum: Number(r.margin_total ?? 0),
      }))
      .sort((a, b) => a._oversizeNum - b._oversizeNum);
  }, [results]);



  // layout styles (simple, clean)
  const styles = {
    page: {
      maxWidth: 1800,
      margin: "0 auto",
      padding: "12px",
      fontFamily: "Segoe UI, Arial, sans-serif",
      background: "white",
      color: "black",
    },

    // simple boxed sections (like a desktop tool)
    section: {
      border: "1px solid #ccc",
      padding: 10,
      marginBottom: 10,
      background: "white",
    },

    title: { margin: "0 0 8px", fontSize: 22, fontWeight: 700 },

    sectionTitle: { fontSize: 13, fontWeight: 600, marginBottom: 6 },

    // compact top controls row
    topBar: {
      display: "flex",
      gap: 10,
      //alignItems: "end",
      alignItems: "flex-start",
      flexWrap: "wrap",
    },

    label: {
      display: "flex",
      flexDirection: "column",
      gap: 4,
      fontSize: 12,
    },

    field: {
      display: "flex",
      flexDirection: "column",
    },

    fieldLabel: {
      marginBottom: 4,
      fontWeight: 600, // optional, match your UI
    },

    helperText: {
      fontSize: 12,
      opacity: 0.75,
      marginTop: 4,
    },

    helperSpacer: {
      height: 16, // keep all fields same height as ones with helper text
    },

    input: {
      padding: "6px 8px",
      fontSize: 13,
      border: "1px solid #999",
      borderRadius: 4,
      minWidth: 160,
    },

    smallInput: {
      padding: "6px 8px",
      fontSize: 13,
      border: "1px solid #999",
      borderRadius: 4,
      width: 90,
    },

    btn: {
      padding: "7px 10px",
      fontSize: 13,
      borderRadius: 4,
      border: "1px solid #333",
      background: "#111",
      color: "white",
      cursor: "pointer",
    },

    // room requirement inputs
    roomsGrid: {
      display: "grid",
      gridTemplateColumns: "repeat(4, minmax(200px, 1fr))",
      gap: 8,
    },

    // results + details split pane
    split: {
      display: "grid",
      gridTemplateColumns: "2fr 1fr",
      gap: 10,
      alignItems: "start",
    },

    tableBox: {
      border: "1px solid #ccc",
      padding: 10,
      background: "white",
      maxHeight: 420,
      overflow: "auto",
    },

    table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },

    th: {
      textAlign: "left",
      padding: "6px 8px",
      borderBottom: "1px solid #ddd",
      position: "sticky",
      top: 0,
      background: "white",
    },

    td: { padding: "6px 8px", borderBottom: "1px solid #eee" },

    row: { cursor: "pointer" },

    selectedRow: { background: "#f0f4ff" },

    details: {
      width: "100%",
      fontFamily: "Consolas, monospace",
      fontSize: 12,
      padding: 10,
      borderRadius: 4,
      border: "1px solid #ccc",
      background: "white",
    },

    err: { color: "#b00020", marginTop: 8, whiteSpace: "pre-wrap" },

    note: { opacity: 0.75, fontSize: 12 },
  };


  return (
    <div style={styles.page}>
      <h1 style={styles.title}>ASHP Combo Calculator</h1>

      {/* TOP BAR (mimics your Tkinter top frame) */}
      <div style={{ ...styles.section, marginBottom: 12 }}>
        <div style={styles.topBar}>

          <div style={styles.field}>
            <div style={styles.fieldLabel}>Manufacturer</div>
            <select
              style={styles.input}
              value={manufacturer}
              onChange={(e) => setManufacturer(e.target.value)}
              disabled={loading}
            >
              {MANUFACTURERS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <div style={styles.helperSpacer} />
          </div>

          <div style={styles.field}>
            <div style={styles.fieldLabel}>&nbsp;</div>
            <button style={styles.btn} onClick={() => loadData(manufacturer)} disabled={loading}>
              Load / Refresh
            </button>
            <div style={styles.helperSpacer} />
          </div>

          <div style={styles.field}>
            <div style={styles.fieldLabel}>Type</div>
            <select
              style={styles.input}
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              disabled={loading}
            >
              {types.map((t) => (
                <option key={t} value={t}>{t === "" ? "(blank)" : t}</option>
              ))}
            </select>
            <div style={styles.helperSpacer} />
          </div>

          <div style={styles.field}>
            <div style={styles.fieldLabel}>Heads / Rooms</div>
            <input
              style={styles.smallInput}
              type="number"
              min={1}
              max={maxHeads}
              value={roomCount}
              onChange={(e) => setRoomCount(clamp(Number(e.target.value || 1), 1, maxHeads))}
              disabled={loading}
            />
            <div style={styles.helperText}>Max: {maxHeads}</div>
          </div>

          <div style={styles.field}>
            <div style={styles.fieldLabel}>&nbsp;</div>
            <button style={styles.btn} onClick={runSolver} disabled={loading}>
              {loading ? "Working..." : "Find Options"}
            </button>
            <div style={styles.helperSpacer} />
          </div>

        </div>

        {error && <div style={styles.err}>{error}</div>}
      </div>

      {/* ROOM INPUTS (mimics rooms_frame) */}
      <div style={{ ...styles.section, marginBottom: 12 }}>
        <div style={styles.sectionTitle}>Room/Head BTU Requirements</div>
        <div style={styles.roomsGrid}>
          {reqs.map((val, idx) => (
            <label key={idx} style={styles.label}>
              Req {idx + 1}
              <input
                style={styles.input}
                value={val}
                onChange={(e) => {
                  const v = e.target.value;
                  setReqs((prev) => {
                    const next = [...prev];
                    next[idx] = v;
                    return next;
                  });
                }}
                placeholder="e.g. 9000"
                inputMode="numeric"
              />
            </label>
          ))}
        </div>
      </div>

      {/* RESULTS + DETAILS (mimics treeview + details textbox) */}
      <div style={styles.split}>
        <div style={{ ...styles.section, flex: 2, overflow: "auto", maxHeight: 420 }}>
          <div style={styles.sectionTitle}>Results</div>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Model</th>
                <th style={styles.th}>Type</th>
                <th style={styles.th}>Indoor Capacity</th>
                <th style={styles.th}>Total Capacity</th>
                <th style={styles.th}>Units</th>
                <th style={styles.th}>Worst Margin</th>
                <th style={styles.th}>Total Oversize</th>
              </tr>
            </thead>
            <tbody>
              {sortedResults.map((r, i) => (
                <tr
                  key={r._rowId}
                  style={selectedRow && r._rowId === selectedRow._rowId ? styles.selectedRow : null}
                  onClick={() => setSelectedRow(r)}
                >
                  <td style={styles.td}>{r.Model}</td>
                  <td style={styles.td}>{r.Type}</td>
                  <td style={styles.td}>{r["Indoor Capacity"] == null ? "" : Number(r["Indoor Capacity"]).toFixed(0)}</td>
                  <td style={styles.td}>{r["Total Capacity"] == null ? "" : Number(r["Total Capacity"]).toFixed(0)}</td>
                  <td style={styles.td}>{r.Units}</td>
                  <td style={styles.td}>{Number(r.worst_margin).toFixed(0)}</td>
                  <td style={styles.td}>{Number(r.margin_total).toFixed(0)}</td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr>
                  <td style={styles.td} colSpan={7}>
                    No results yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div style={{ ...styles.section, flex: 1 }}>
          <div style={styles.sectionTitle}>Details</div>
          <textarea
            style={styles.details}
            rows={detailsRows}
            value={detailsText}
            readOnly
            placeholder="Select a result row to see details."
          />
        </div>
        <div style={{ fontSize: 12, marginTop: 6 }}>
          Selected: {selectedRow ? "YES" : "NO"}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";

// import for AI agent helpers
import { aiRecommend, buildAiDetailsText } from "./aiAgent";
import AiChatPanel from "./AiChatPanel";

const MANUFACTURERS = ["All", "Fujitsu", "LG"];

// just used for Ai dev vs prod environment
function ComingSoonTab() {
  return (
    <div style={{
      padding: "40px",
      textAlign: "center",
      borderRadius: "12px",
      background: "#f5f5f5",
      marginTop: "20px"
    }}>
      <h2>AI System Design</h2>
      <p>This feature is coming soon.</p>
    </div>
  );
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function toNumberOrNull(v) {
  const x = Number(String(v).trim());
  return Number.isFinite(x) ? x : null;
}

function compareValues(a, b, dir) {
  const av = a ?? "";
  const bv = b ?? "";

  const an = toNumberOrNull(av);
  const bn = toNumberOrNull(bv);

  // numeric compare if possible
  if (an !== null && bn !== null) {
    return dir === "asc" ? an - bn : bn - an;
  }

  // fallback string compare
  const as = String(av).toLowerCase();
  const bs = String(bv).toLowerCase();

  if (as < bs) return dir === "asc" ? -1 : 1;
  if (as > bs) return dir === "asc" ? 1 : -1;
  return 0;
}

// Functions to help sort unit combos (7+7+7 < 7+7+9 < 7+7+12 < 7+9+9 < 7+9+12 … < 9+12+12 …)
function parseUnitsCombo(s) {
  const parts = String(s ?? "")
    .split("+")
    .map((p) => Number(String(p).trim()))
    .filter((n) => Number.isFinite(n));

  // normalize inside-combo order so "12+7" behaves like "7+12"
  parts.sort((a, b) => a - b);

  return parts;
}

function compareUnitsCombo(aUnits, bUnits, dir) {
  const a = parseUnitsCombo(aUnits);
  const b = parseUnitsCombo(bUnits);

  // empty values go last in ascending, first in descending
  if (a.length === 0 && b.length === 0) return 0;
  if (a.length === 0) return dir === "asc" ? 1 : -1;
  if (b.length === 0) return dir === "asc" ? -1 : 1;

  // shorter combo first (2-head before 3-head) if you want that behavior
  if (a.length !== b.length) {
    return dir === "asc" ? a.length - b.length : b.length - a.length;
  }

  // lexicographic compare
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return dir === "asc" ? a[i] - b[i] : b[i] - a[i];
  }
  return 0;
}

function ResultsSection({
  aiUserText, setAiUserText, aiLoading, aiError, runAi,
  sortKey, setSortKey, sortColumns, sortDir, setSortDir,
  searchQuery, setSearchQuery,
  sortedResults, results, selectedRow, setSelectedRow,
  styles
}) {
  return (
    <>
      {/* Sticky header */}
      <div style={styles.resultsStickyHeader}>
        <div style={styles.sectionTitle}>Results</div>

          <div style={styles.resultsControls}>
            <label>
              Sort by{" "}
              <select
                value={sortKey}
                style={styles.input}
                onChange={(e) => {
                  console.log("🔽 Sort column changed:", e.target.value);
                  setSortKey(e.target.value);
                }}
              >
                {sortColumns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>

            <button
              type="button"
              style={styles.btn}
              onClick={() => {
                setSortDir((d) => {
                  const next = d === "asc" ? "desc" : "asc";
                  console.log("🔁 Sort direction toggled:", d, "→", next);
                  return next;
                });
              }}
            >
              {sortDir === "asc" ? "Ascending ▲" : "Descending ▼"}
            </button>

            <label style={{ display: "block", marginBottom: 6 }}>
              Search model: 
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  console.log("🔤 Search input changed:", e.target.value);
                  setSearchQuery(e.target.value);
                }}
                placeholder="Search model… e.g. AOUH30KUAS1"
                style={{ ...styles.input, width: 240, marginLeft: 8 }}
              />
            </label>

          </div>
        </div>

        {/* Table content */}
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Manufacturer</th>
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
            {sortedResults.map((r, i) => {
              console.log("🟦 Rendering row:", r)
              return (
                <tr
                  key={r._rowId}
                  style={selectedRow && r._rowId === selectedRow._rowId ? styles.selectedRow : null}
                  onClick={() => {
                    console.log("🟦 Row clicked:", r);
                    setSelectedRow(r);

                    // if (r.__aiCandidate) {
                    //   setDetailsText(buildAiDetailsText(r));
                    // } else {
                    //   setDetailsText(existingDetailsTextForRow(r)); // whatever you already do
                    // }

                  }}
                >
                  <td style={styles.td}>{r.Manufacturer}</td>
                  <td style={styles.td}>{r.Model}</td>
                  <td style={styles.td}>{r.Type}</td>
                  <td style={styles.tdCenter}>
                    {r["Indoor Capacity"] == null ? "" : Number(r["Indoor Capacity"]).toFixed(0)}
                  </td>
                  <td style={styles.tdCenter}>
                    {r["Total Capacity"] == null ? "" : Number(r["Total Capacity"]).toFixed(0)}
                  </td>
                  <td style={styles.tdCenter}>{r.Units}</td>
                  <td style={styles.tdCenter}>{Number(r.worst_margin).toFixed(0)}</td>
                  <td style={styles.tdCenter}>{Number(r.margin_total).toFixed(0)}</td>
                </tr>
              )
            })}

            {/* Empty state should use sortedResults, not results */}
            {sortedResults.length === 0 && (
              <tr>
                <td style={styles.td} colSpan={7}>
                  {results.length === 0
                    ? "No results yet."
                    : "No matches for your search."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
    </>
  );
}

function buildCalculatorStateFromConduit(load) {
  if (!load || typeof load !== "object") {
    return null;
  }

  // adjust these fields to your real payload shape
  const manufacturer = load.manufacturer || "Fujitsu";

  // try several likely shapes for room/head loads
  let rawReqs = [];

  if (Array.isArray(load.reqs)) {
    rawReqs = load.reqs;
  } else if (Array.isArray(load.rooms)) {
    rawReqs = load.rooms.map((r) =>
      r?.heating_load_btuh ??
      r?.heating_btuh ??
      r?.load_btuh ??
      r?.required_btuh ??
      ""
    );
  } else if (Array.isArray(load.head_requirements)) {
    rawReqs = load.head_requirements;
  }

  const reqs = rawReqs
    .map((v) => String(v ?? "").trim())
    .filter((v) => v !== "");

  return {
    manufacturer,
    reqs,
    roomCount: Math.max(1, reqs.length),
  };
}

export default function App() {
  // making sure ai portion doesnt show on prod until ready
  const ENABLE_AI =
    import.meta.env.VITE_ENABLE_AI === "true" ||
    import.meta.env.DEV;
  console.log("VITE_ENABLE_AI =", import.meta.env.VITE_ENABLE_AI);

  // --- top bar state ---
  const [manufacturer, setManufacturer] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [types, setTypes] = useState(["All"]);

  const [maxHeads, setMaxHeads] = useState(8);
  const [roomCount, setRoomCount] = useState(1);

  // --- dynamic room requirements ---
  const [reqs, setReqs] = useState(["9000"]); // same default vibe as your GUI

  // --- results ---
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedRow, setSelectedRow] = useState(null);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // --- sorting ---
  const DEFAULT_SORT_KEY = "Total Oversize";

  const [sortKey, setSortKey] = useState(DEFAULT_SORT_KEY);
  const [sortDir, setSortDir] = useState("asc");

  const sortColumns = ["Total Oversize", "Worst Margin", "Indoor Capacity", "Total Capacity", "Model", "Type", "Units"]; 

  // setting variables for AI agent integration
  const [aiUserText, setAiUserText] = useState("");
  const [messages, setMessages] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");

  const [roomCatalog, setRoomCatalog] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]); //(["whole_unit"]); // default

  // setting logic for fetching conduit data from generator upload
  const [incomingLoad, setIncomingLoad] = useState(null);
  const [loadImported, setLoadImported] = useState(false);

  // IMPORTANT: origin strings do not end with "/"
  const GENERATOR_ORIGIN =
    import.meta.env.VITE_GENERATOR_ORIGIN ||
    "https://wonderful-desert-0055d690f-staging.eastus2.1.azurestaticapps.net";

  // tell parent iframe host that calculator is ready
  useEffect(() => {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(
        { type: "calculator_ready" },
        GENERATOR_ORIGIN
      );
      console.log("📤 Sent calculator_ready to parent:", GENERATOR_ORIGIN);
    }
  }, [GENERATOR_ORIGIN]);

  useEffect(() => {
    if (!incomingLoad) return;

    console.log("📦 Incoming conduit load:", incomingLoad);

    const mapped = buildCalculatorStateFromConduit(incomingLoad);

    if (!mapped) {
      console.log("⚠️ Could not map incoming conduit load");
      return;
    }

    console.log("🧭 Mapped conduit load for calculator:", mapped);

    if (mapped.manufacturer) {
      setManufacturer(mapped.manufacturer);
    }

    if (mapped.roomCount) {
      setRoomCount(mapped.roomCount);
    }

    if (mapped.reqs?.length) {
      setReqs(mapped.reqs);
    }

    setSelectedRow(null);
    setResults([]);
    setError("");
    setLoadImported(true);
  }, [incomingLoad]);

  // receive conduit load from proposal generator
  useEffect(() => {
    function handleMessage(event) {
      if (event.origin !== GENERATOR_ORIGIN) {
        console.log("⛔ Ignoring message from unexpected origin:", event.origin);
        return;
      }

      if (!event?.data) return;

      console.log("📩 Calculator received message:", event.data);

      if (event.data.type === "conduit_load") {
        setIncomingLoad(event.data.payload || null);
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [GENERATOR_ORIGIN]);

  useEffect(() => {
    if (!loadImported) return;
    if (!reqs.length) return;

    const timer = setTimeout(() => {
      runSolver();
      setLoadImported(false);
    }, 150);

    return () => clearTimeout(timer);
  }, [loadImported, reqs]);

  useEffect(() => {
    console.log("Fetching AI catalog...");

    fetch("/api/ai/catalog", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        loads: incomingLoad,
      }),
    })
      .then(async (r) => {
        console.log("Catalog response status:", r.status);
        console.log("Catalog response content-type:", r.headers.get("content-type"));

        const text = await r.text();
        console.log("Catalog raw response:", text.slice(0, 500));

        return JSON.parse(text);
      })
      .then((data) => {
        console.log("Catalog data:", data);
        setRoomCatalog(data);
      })
      .catch((e) => {
        console.error("Catalog fetch error:", e);
        setAiError(e.message || String(e));
      });
  }, []);

  // function to run AI agent
  async function runAi(textOverride, messages = []) {
    const text = (textOverride ?? aiUserText).trim();

    console.log("Room Catalog for AI agent:", roomCatalog);
    console.log("selectedIds:", selectedIds);
    console.log("🤖 Running AI agent with user text:", text);
    console.log("🤖 Full AI chat history:", messages);

    if (!roomCatalog) {
      setAiError("Room catalog not loaded yet.");
      return null; // IMPORTANT: return something
    }

    try {
      setAiLoading(true);
      setAiError("");

      const payload = await aiRecommend({
        user_text: text,
        //selected_ids: selectedIds,
        chat_history: messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        loads: incomingLoad,
        // intent_model: "gpt-5.2",
      });

      console.log("AI payload intent:", payload?.intent);
      console.log("AI payload rec:", payload?.rec);
      console.log("AI draft warnings:", payload?.rec?.warnings);
      console.log("AI draft candidates:", payload?.rec?.drafts?.[0]?.candidates);

      console.log("🤖 AI RAW PAYLOAD:", payload);

      const draft = payload?.rec?.drafts?.[0];
      console.log("📦 AI DRAFT:", draft);

      // need to make sure aiRows has __aiCandidate set to build AI specific details pane for user
      const aiRows = (draft?.candidates || []).map((c, i) => ({
        ...c,
        __aiCandidate: c,   // 👈 flag that this row came from AI
        __aiMeta: payload?.rec || {}, // optional but useful later
        _rowId: `ai-${i}-${c.outdoor_model || c.Model || "row"}`
      }));
      console.log("📊 AI ROWS GENERATED:", aiRows);

      setResults(aiRows);
      setSelectedRow(null);

      return payload; // ✅ lets AiChatPanel show questions
    } catch (e) {
      setAiError(e.message || String(e));
      throw e; // ✅ so AiChatPanel can also show an "Error:" message if you want
    } finally {
      setAiLoading(false);
    }
  }

  // formatting numbers helper
  const fmt = (v, digits = 0) => {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    return n.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };

  // details autosize like your Tkinter Text box
  const detailsText = useMemo(() => {
    console.log("📝 computing detailsText, selectedRow =", selectedRow);

    if (!selectedRow) return "";

    // ✅ AI row details
    if (selectedRow.__aiCandidate) {
      console.log("🧾 Building AI details text for AI row:", selectedRow.__aiCandidate);
      return buildAiDetailsText(selectedRow);
    }
    

    const r = selectedRow;
    const manufacturer = r.Manufacturer ?? "";
    const model = r.Model ?? "";
    const type = r.Type ?? "";
    const units = r.Units ?? "";
    const indoorCap = r["Indoor Capacity"] ?? "";
    const totalCap = r["Total Capacity"] ?? "";
    const mapping = Array.isArray(r.mapping) ? r.mapping : [];

    // New fields (these exist in the row, but you won’t show them as table columns)
    const op_watts = r["Op. Watts/Htg"];
    const breaker = r["Breaker Req."];
    const btu5 = r["BTU @ 5*F"];
    const btu0 = r["BTU @ 0*F"];
    const tonnage = r["Tonnage"];
    const seer2 = r["SEER2"];
    const eer2 = r["EER2"];
    const hspf2 = r["HSPF2"];
    
    console.log("🧾 details of selected row data:", r)

    const lines = [
      `Manufacturer: ${manufacturer}`,
      `Model: ${model}`,
      "Performance:",
      `  Op. Watts/Htg: ${fmt(op_watts)}`,
      `  Breaker Req.: ${fmt(breaker)}`,
      `  BTU @ 5°F: ${fmt(btu5)} | BTU @ 0°F: ${fmt(btu0)}`,
      `  Tonnage: ${fmt(tonnage, 2)} | SEER2: ${fmt(seer2, 1)} | EER2: ${fmt(eer2, 1)} | HSPF2: ${fmt(hspf2, 1)}`,
      "",
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

  useEffect(() => {
    console.log("🧾 detailsText updated:", detailsText);
  }, [detailsText]);

  // --- load/refresh meta like your load_data() ---
  async function loadData(m = manufacturer) {
    setError("");
    setLoading(true);
    setResults([]);
    setSelectedRow(null);

    try {
      console.log("manufacturer before fetch:", m);

      const res = await fetch(`/api/meta?manufacturer=${encodeURIComponent(m)}`);
      const data = await res.json();

      console.log("meta response status:", res.status);
      console.log("meta response data:", data);

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

  useEffect(() => {
    console.log("📌 selectedRow updated:", selectedRow);
  }, [selectedRow]);

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
        setSelectedRow(null);
      }

    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // Sum all the reqs
  const totalReq = useMemo(() => {
    return reqs.reduce((sum, v) => sum + (toNumberOrNull(v) ?? 0), 0);
  }, [reqs]);


  // allowign searching to sort as well
  const filteredResults = results.filter((row) => {
    if (!searchQuery.trim()) return true;

    const q = searchQuery.toLowerCase();

    return (
      row.Model?.toLowerCase().includes(q) ||
      row.Manufacturer?.toLowerCase().includes(q) ||
      row.Units?.toLowerCase().includes(q) // optional
    );
  });

  // adjust these to match your real field names
  const getModelText = (row) => String(row.Model ?? row.model ?? "");
  const getMfrText   = (row) => String(row.Manufacturer ?? row.manufacturer ?? "");
  const getUnitsText = (row) => String(row.Units ?? row.units ?? "");

  const q = searchQuery.trim().toLowerCase();

  // const visibleResults = (() => {
  //   console.log("🔍 Recomputing visibleResults");

  //   const q = searchQuery.trim().toLowerCase();
  //   console.log("🔎 Normalized query:", q);

  //   const filtered = results.filter((r, idx) => {
  //     const model = String(r.Model ?? "").toLowerCase();
  //     const units = String(r.Units ?? "").toLowerCase();

  //     const match = !q || model.includes(q) || units.includes(q);

  //     if (q && idx < 5) {
  //       console.log("   Row check:", {
  //         model,
  //         units,
  //         match,
  //       });
  //     }

  //     return match;
  //   });

  //   console.log(
  //     `📊 Filtered results: ${filtered.length} / ${results.length}`
  //   );

  //   const sorted = [...filtered].sort((a, b) => {
  //     if (sortKey === "Units") {
  //       return compareUnitsCombo(a.Units, b.Units, sortDir);
  //     }
  //     return compareValues(a[sortKey], b[sortKey], sortDir);
  //   });

  //   console.log("📐 Sorted results length:", sorted.length);

  //   return sorted;
  // })();

  // Organizing list of models in order based on total oversize
  // sort results by Total Oversize (margin_total) smallest -> largest
  const sortedResults = useMemo(() => {
    console.log("📊 Recomputing sortedResults", {
      sortKey,
      sortDir,
      resultCount: filteredResults.length,
    });

    return [...filteredResults]
      .map((r, idx) => ({
        ...r,
        _rowId: `${r.Model}-${r.Type}-${r.Units}-${idx}`,
        "Total Oversize": Number(r.margin_total ?? 0),
        "Worst Margin": Number(r.worst_margin ?? 0),
        //"Total Oversize": toNumberOrNull(r.margin_total),
        //"Worst Margin": toNumberOrNull(r.worst_margin),
        "Indoor Capacity": toNumberOrNull(r["Indoor Capacity"]),
        "Total Capacity": toNumberOrNull(r["Total Capacity"]),
        "Units": r.Units,
        "Model": r.Model,
        "Type": r.Type,
      }))
      
      .sort((a, b) => {
        const av = a?.[sortKey];
        const bv = b?.[sortKey];

        if (sortKey === "Units") {
          //console.log("UNITS compare", { av, bv });
          return compareUnitsCombo(av, bv, sortDir);
        }

        // (optional) noisy debug; remove once verified
        //console.log("🧮 Compare", { sortKey, sortDir, a: av, b: bv });

        return compareValues(av, bv, sortDir);
      });
  }, [filteredResults, sortKey, sortDir]);

  // layout styles (simple, clean)
  const styles = {
    page: {
      //maxWidth: 1800,
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
      // hard safety against weird inherited positioning:
      position: "relative",
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
      gridTemplateColumns: "repeat(auto-fill, 120px)", //"repeat(auto-fit, minmax(100px, 1fr))", // i dont want to autofitting across the whole width
      gap: 12,
      alignItems: "start",
    },

    reqLabel: {
      display: "flex",
      flexDirection: "column",
      gap: 4, // now works because span + input are element children
      fontSize: 12,
    },

    reqLabelText: {
      lineHeight: 1.1,
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
      top: 62,
      background: "white",
      zIndex: 10,
    },

    td: { 
      padding: "6px 8px", 
      borderBottom: "1px solid #eee",
    },

    tdCenter: {
      padding: "6px 8px",
      borderBottom: "1px solid #eee",
      textAlign: "center",
    },

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
      // ✅ force visible text
      color: "#111",
      WebkitTextFillColor: "#111",
      // ✅ in case something global is dimming it
      opacity: 1,
    },

    err: { color: "#b00020", marginTop: 8, whiteSpace: "pre-wrap" },

    note: { opacity: 0.75, fontSize: 12 },

    resultsStickyHeader: {
      position: "sticky",
      top: 0,
      zIndex: 20,
      background: "#fff",          // important so the table doesn't show through
      paddingBottom: 8,
      borderBottom: "1px solid #ddd",
    },

    resultsControls: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      flexWrap: "wrap",
    },

  };


  return (
    <div style={styles.page}>
      <h1 style={styles.title}>ASHP Combo Calculator</h1>

      <div className="appShell">

        {/* TOP BAR (mimics your Tkinter top frame) */}
        <section className="controls">
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
          <form
            style={{ ...styles.section, marginBottom: 12 }}
            onSubmit={(e) => {
              e.preventDefault();
              if (!loading) runSolver();
            }}
          >
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: 6
            }}>
              <div style={styles.sectionTitle}>
                Room/Head BTU Requirements
              </div>

              <div style={{
                fontWeight: 600,
                fontSize: 12,
                opacity: 0.85
              }}>
                Total Req: {Number(totalReq).toFixed(0)} BTU
              </div>
            </div>
            <div style={styles.roomsGrid}>
              {reqs.map((val, idx) => (
                <label key={idx} style={styles.reqLabel}>
                  <span style={styles.reqLabelText}>Req {idx + 1}</span>
                  <input
                    style={{ ...styles.input, width: "100%", boxSizing: "border-box", minWidth: 0 }}
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
            <div style={{ fontSize: 11, color: "#666" }}>
              Press Enter to find options
            </div>
          </form>
        </section>

        {/* AI + RESULTS */}
        <section
          className="results"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 32%)",
            gap: 16,
            alignItems: "start",
            width: "100%",
            minWidth: 0,
          }}
        >
          {/* LEFT — Results */}
          <div
            style={{
              ...styles.section,
              minWidth: 0,
              overflowX: "auto",
              boxSizing: "border-box",
              maxHeight: "60vh",
            }}
          >
            <ResultsSection
              aiUserText={aiUserText}
              setAiUserText={setAiUserText}
              aiLoading={aiLoading}
              aiError={aiError}
              runAi={runAi}
              sortKey={sortKey}
              setSortKey={setSortKey}
              sortColumns={sortColumns}
              sortDir={sortDir}
              setSortDir={setSortDir}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              sortedResults={sortedResults}
              results={results}
              selectedRow={selectedRow}
              setSelectedRow={setSelectedRow}
              styles={styles}
            />
          </div>

          {/* RIGHT — AI */}
          <div
            style={{
              ...styles.section,
              minWidth: 0,
              boxSizing: "border-box",
            }}
          >
            {ENABLE_AI ? (
              <AiChatPanel
                aiUserText={aiUserText}
                setAiUserText={setAiUserText}
                aiLoading={aiLoading}
                aiError={aiError}
                roomCatalog={roomCatalog}
                selectedIds={selectedIds}
                setSelectedIds={setSelectedIds}
                onSend={runAi}
              />
            ) : (
              <ComingSoonTab title="AI System Design" message="This feature is coming soon." />
            )}
          </div>
        </section>
          
        <section className="details">
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
        </section>
      </div>
    </div>
  );
}

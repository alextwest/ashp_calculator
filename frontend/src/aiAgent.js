// Script containing helpers to run the AI agent on the ashp calculator to propose a system design based on users needs and thought process

// ---- 1) API call: summary + user text -> { intent, rec }
export async function aiRecommend(body) {
  console.log("Hitting /ai/recommend API")
  const resp = await fetch("/api/ai/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  console.log("Body sent to AI recommend API:", body);
  console.log("Raw response from AI recommend API:", resp);

  if (!resp.ok) {
    const txt = await resp.text();
    console.error("AI recommend failed:", resp.status, txt);
    throw new Error(`AI recommend failed (${resp.status}): ${txt}`);
  }

  return await resp.json();
}

function computeMarginsFromMapping(mapping) {
  const pairs = Array.isArray(mapping) ? mapping : [];
  if (!pairs.length) return { worst_margin: null, margin_total: null };

  const deltas = pairs
    .map(([req, cap]) => (Number(cap) || 0) - (Number(req) || 0));

  return {
    worst_margin: Math.min(...deltas),
    margin_total: deltas.reduce((a, b) => a + b, 0),
  };
}

// ---- 2) Map AI candidates -> existing table rows
export function candidatesToRows(draft) {
  const candidates = draft?.candidates || [];
  const distribution = draft?.distribution || "";

  return candidates.map((c, i) => {

    const mapping = Array.isArray(c.mapping) ? c.mapping : [];

    const { worst_margin, margin_total } =
      computeMarginsFromMapping(mapping);

    return {

      _rowId: `ai-${i}-${c.outdoor_model}-${c.unit_mix || ""}`,

      // existing table columns
      Model: c.outdoor_model ?? "",
      Type: c.type || (distribution === "ductless" ? "Non-ducted" : "Ducted"),
      "Indoor Capacity": c.indoor_capacity ?? c.indoorCap ?? null,             // keep blank if not available
      "Total Capacity": c.total_capacity ?? null,
      Units: c.unit_mix || "",
      mapping,

      // reuse your columns to show useful “fit” info
      worst_margin,
      margin_total,

      // keep full payload for Details
      __aiCandidate: c,
      __aiMeta: {
        system_name: draft?.system_name,
        distribution: draft?.distribution,
        indoor_head_count: draft?.indoor_head_count,
        margin_pct: draft?.margin_pct,
        required_heat_btu_hr: draft?.required_heat_btu_hr,
        selected_room_labels: draft?.selected_room_labels,
        selected_rooms: draft?.selected_rooms,
        room_load_lookup: draft?.room_load_lookup,
      },
    };
  });
}

// ---- 3) Build Details textarea text when an AI row is selected
export function buildAiDetailsText(row) {
  const c = row?.__aiCandidate;
  const m = row?.__aiMeta;
  if (!c || !m) return "";

  const lines = [];

  const fmt = (v, digits = 0) =>
    typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "";

  const fmtPct = (v, digits = 1) =>
    typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(digits)}%` : "";

  const actualLoad =
    typeof m.actual_heat_btu_hr === "number"
      ? m.actual_heat_btu_hr
      : typeof m.selected_heat_btu_hr === "number"
      ? m.selected_heat_btu_hr
      : typeof m.required_heat_btu_hr === "number" && typeof m.margin_pct === "number"
      ? m.required_heat_btu_hr / (1 + m.margin_pct)
      : null;

  const requiredLoad =
    typeof m.required_heat_btu_hr === "number" ? m.required_heat_btu_hr : null;

  const deliveredCapacity =
    typeof c.total_capacity === "number"
      ? c.total_capacity
      : typeof c.btu_0f === "number"
      ? c.btu_0f
      : typeof c.btu_5f === "number"
      ? c.btu_5f
      : null;

  const capacityMargin =
    typeof deliveredCapacity === "number" && typeof requiredLoad === "number"
      ? deliveredCapacity - requiredLoad
      : null;

  const capacityMarginPct =
    typeof capacityMargin === "number" &&
    typeof requiredLoad === "number" &&
    requiredLoad > 0
      ? capacityMargin / requiredLoad
      : null;

  lines.push("AI Recommendation");
  lines.push(`System: ${m.system_name || ""}`);
  lines.push(`Distribution: ${m.distribution || ""}`);
  lines.push(`Heads: ${m.indoor_head_count ?? ""}`);

  if (typeof m.margin_pct === "number") {
    lines.push(`Design Margin: ${fmtPct(m.margin_pct, 0)}`);
  }

  if (typeof actualLoad === "number") {
    lines.push(`Actual Load: ${fmt(actualLoad)} BTU/hr`);
  }

  if (typeof requiredLoad === "number") {
    lines.push(`Required Load: ${fmt(requiredLoad)} BTU/hr`);
  }

  if (typeof deliveredCapacity === "number") {
    lines.push(`Candidate Capacity: ${fmt(deliveredCapacity)} BTU/hr`);
  }

  if (typeof capacityMargin === "number") {
    lines.push(`Capacity Margin: ${fmt(capacityMargin)} BTU/hr`);
  }

  if (typeof capacityMarginPct === "number") {
    lines.push(`Capacity Margin %: ${fmtPct(capacityMarginPct, 1)}`);
  }

  lines.push("");


  const rooms = Array.isArray(m.selected_room_labels) ? m.selected_room_labels : [];
  if (rooms.length) {
    lines.push(`Rooms (${rooms.length}):`);
    rooms.slice(0, 40).forEach((roomName) => lines.push(`  • ${roomName}`));
    if (rooms.length > 40) lines.push(`  … +${rooms.length - 40} more`);
    lines.push("");
  }

  // Optional per-room request details
  // Expected best shape:
  // m.room_requests = [
  //   { room_name, actual_load, adjusted_load, req_btu, assigned_capacity, margin_btu, margin_pct }
  // ]
  const roomRequests = Array.isArray(m.room_requests) ? m.room_requests : [];

  if (roomRequests.length) {
    lines.push("Room Requests:");
    roomRequests.forEach((r, idx) => {
      const label = r.room_name || `Room ${idx + 1}`;
      lines.push(`  ${idx + 1}. ${label}`);

      if (typeof r.actual_load === "number") {
        lines.push(`     Actual: ${fmt(r.actual_load)} BTU/hr`);
      }

      if (typeof r.adjusted_load === "number") {
        lines.push(`     With Margin: ${fmt(r.adjusted_load)} BTU/hr`);
      }

      if (typeof r.req_btu === "number") {
        lines.push(`     Requested Head: ${fmt(r.req_btu)} BTU`);
      }

      if (typeof r.assigned_capacity === "number") {
        lines.push(`     Assigned Capacity: ${fmt(r.assigned_capacity)} BTU`);
      }

      if (typeof r.margin_btu === "number") {
        lines.push(`     Margin: ${fmt(r.margin_btu)} BTU`);
      }

      if (typeof r.margin_pct === "number") {
        lines.push(`     Margin %: ${fmtPct(r.margin_pct, 1)}`);
      }
    });
    lines.push("");
  }

  lines.push("Selected Candidate");
  lines.push(`Outdoor: ${c.outdoor_model || ""}`);
  lines.push(`Mix: ${c.unit_mix || ""}`);

  if (typeof c.worst_margin === "number") {
    lines.push(`Worst Margin: ${fmt(c.worst_margin)}`);
  } else if (typeof row?.worst_margin === "number") {
    lines.push(`Worst Margin: ${fmt(row.worst_margin)}`);
  }

  if (typeof c.margin_total === "number") {
    lines.push(`Total Oversize: ${fmt(c.margin_total)}`);
  } else if (typeof row?.margin_total === "number") {
    lines.push(`Total Oversize: ${fmt(row.margin_total)}`);
  }

  if (c.btu_5f != null) lines.push(`BTU @ 5°F: ${fmt(Number(c.btu_5f))}`);
  if (c.btu_0f != null) lines.push(`BTU @ 0°F: ${fmt(Number(c.btu_0f))}`);
  if (c.total_capacity != null) lines.push(`Total Capacity: ${fmt(Number(c.total_capacity))}`);
  lines.push("");

  if (c.breaker_req != null) lines.push(`Breaker: ${fmt(Number(c.breaker_req))}A`);
  if (c.op_watts_htg != null) lines.push(`Op. Watts (Htg): ${fmt(Number(c.op_watts_htg))}`);
  lines.push(`SEER2: ${c.seer2 ?? ""}  EER2: ${c.eer2 ?? ""}  HSPF2: ${c.hspf2 ?? ""}`);

  if (c.meets_required != null) {
    lines.push("");
    lines.push(`Meets Required: ${c.meets_required ? "Yes" : "No"}`);
    if (typeof c.delta_btu === "number") {
      lines.push(`Delta: ${fmt(c.delta_btu)} BTU`);
    }
  }

  return lines.join("\n");
}
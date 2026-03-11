// Script containing helpers to run the AI agent on the ashp calculator to propose a system design based on users needs and thought process

// ---- 1) API call: summary + user text -> { intent, rec }
export async function aiRecommend(body) {
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
  lines.push("AI Recommendation");
  lines.push(`System: ${m.system_name || ""}`);
  lines.push(`Distribution: ${m.distribution || ""}`);
  lines.push(`Heads: ${m.indoor_head_count ?? ""}`);

  if (typeof m.margin_pct === "number") lines.push(`Margin: ${Math.round(m.margin_pct * 100)}%`);
  if (typeof m.required_heat_btu_hr === "number") lines.push(`Required Heat: ${m.required_heat_btu_hr.toFixed(0)} BTU/hr`);
  lines.push("");

  const rooms = m.selected_room_labels || [];
  if (rooms.length) {
    lines.push(`Rooms (${rooms.length}):`);
    rooms.slice(0, 40).forEach(r => lines.push(`  • ${r}`));
    if (rooms.length > 40) lines.push(`  … +${rooms.length - 40} more`);
    lines.push("");
  }

  lines.push("Selected Candidate");
  lines.push(`Outdoor: ${c.outdoor_model || ""}`);
  lines.push(`Mix: ${c.unit_mix || ""}`);

  lines.push(`Worst margin: ${Number(r.worst_margin ?? 0).toFixed(0)}`);
  lines.push(`Total oversize: ${Number(r.margin_total ?? 0).toFixed(0)}`);

  if (c.btu_5f != null) lines.push(`BTU @5F: ${Number(c.btu_5f).toFixed(0)}`);
  if (c.btu_0f != null) lines.push(`BTU @0F: ${Number(c.btu_0f).toFixed(0)}`);
  if (c.total_capacity != null) lines.push(`Total: ${Number(c.total_capacity).toFixed(0)}`);
  lines.push("");

  if (c.breaker_req != null) lines.push(`Breaker: ${Number(c.breaker_req).toFixed(0)}A`);
  if (c.op_watts_htg != null) lines.push(`OpWatts(Htg): ${Number(c.op_watts_htg).toFixed(0)}`);
  lines.push(`SEER2: ${c.seer2 ?? ""}  EER2: ${c.eer2 ?? ""}  HSPF2: ${c.hspf2 ?? ""}`);

  if (c.meets_required != null) {
    lines.push("");
    lines.push(`Meets required: ${c.meets_required ? "Yes" : "No"}`);
    if (typeof c.delta_btu === "number") lines.push(`Delta: ${c.delta_btu.toFixed(0)} BTU`);
  }

  return lines.join("\n");
}
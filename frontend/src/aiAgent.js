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
  if (!c) return "";

  const lines = [];

  const num = (v, digits = 0) =>
    typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "";

  const val = (...values) => {
    for (const v of values) {
      if (v !== undefined && v !== null && v !== "") return v;
    }
    return "";
  };

  lines.push("AI Recommendation");

  // Meta info if present
  const draft = m?.drafts?.[0] || null;
  const intent = draft?.intent || m?.intent || null;

  const systemName = val(
    m?.system_name,
    draft?.system_name,
    intent?.system_name
  );

  const distribution = val(
    m?.distribution,
    draft?.distribution,
    intent?.distribution
  );

  const headCount = val(
    m?.indoor_head_count,
    draft?.indoor_head_count,
    intent?.indoor_head_count,
    c?.heads_detected
  );

  const marginPct = val(
    m?.margin_pct,
    draft?.margin_pct,
    intent?.margin_pct
  );

  const requiredHeat = val(
    m?.required_heat_btu_hr,
    draft?.required_heat_btu_hr,
    intent?.required_heat_btu_hr
  );

  if (systemName) lines.push(`System: ${systemName}`);
  if (distribution) lines.push(`Distribution: ${distribution}`);
  if (headCount !== "") lines.push(`Heads: ${headCount}`);
  if (typeof marginPct === "number") lines.push(`Margin: ${Math.round(marginPct * 100)}%`);
  if (typeof requiredHeat === "number") lines.push(`Required Heat: ${requiredHeat.toFixed(0)} BTU/hr`);

  const rooms =
    m?.selected_room_labels ||
    draft?.selected_room_labels ||
    intent?.selected_room_labels ||
    [];

  if (lines.length > 1 || rooms.length) lines.push("");

  if (rooms.length) {
    lines.push(`Rooms (${rooms.length}):`);
    rooms.slice(0, 40).forEach((r) => lines.push(`  • ${r}`));
    if (rooms.length > 40) lines.push(`  … +${rooms.length - 40} more`);
    lines.push("");
  }

  lines.push("Selected Candidate");
  lines.push(`Outdoor: ${val(c.outdoor_model, c.Model)}`);
  lines.push(`Type: ${val(c.type, c.Type)}`);
  lines.push(`Mix: ${val(c.unit_mix, c.Units)}`);

  const worstMargin = val(c.worst_margin, c["Worst Margin"]);
  const totalOversize = val(c.margin_total, c["Total Oversize"]);

  if (worstMargin !== "") lines.push(`Worst Margin: ${num(Number(worstMargin))}`);
  if (totalOversize !== "") lines.push(`Total Oversize: ${num(Number(totalOversize))}`);

  const btu5 = val(c.btu_5f, c["BTU @ 5*F"], c["BTU @5F"]);
  const btu0 = val(c.btu_0f, c["BTU @ 0*F"], c["BTU @0F"]);
  const totalCap = val(c.total_capacity, c["Total Capacity"]);
  const indoorCap = val(c.indoor_capacity, c["Indoor Capacity"]);

  if (btu5 !== "") lines.push(`BTU @ 5°F: ${num(Number(btu5))}`);
  if (btu0 !== "") lines.push(`BTU @ 0°F: ${num(Number(btu0))}`);
  if (totalCap !== "") lines.push(`Total Capacity: ${num(Number(totalCap))}`);
  if (indoorCap !== "") lines.push(`Indoor Capacity: ${num(Number(indoorCap))}`);

  lines.push("");

  const breaker = val(c.breaker_req, c["Breaker Req."]);
  const watts = val(c.op_watts_htg, c["Op. Watts/Htg"]);
  const tonnage = val(c.tonnage, c.Tonnage);
  const seer2 = val(c.seer2, c.SEER2);
  const eer2 = val(c.eer2, c.EER2);
  const hspf2 = val(c.hspf2, c.HSPF2);

  if (breaker !== "") lines.push(`Breaker: ${num(Number(breaker))}A`);
  if (watts !== "") lines.push(`Op. Watts (Htg): ${num(Number(watts))}`);
  if (tonnage !== "") lines.push(`Tonnage: ${num(Number(tonnage), 2)}`);
  if (seer2 !== "" || eer2 !== "" || hspf2 !== "") {
    lines.push(`SEER2: ${seer2 ?? ""}  EER2: ${eer2 ?? ""}  HSPF2: ${hspf2 ?? ""}`);
  }

  const mapping = Array.isArray(c.mapping) ? c.mapping : [];

  if (mapping.length) {
    lines.push("");
    lines.push("Head Assignment:");

    mapping.forEach((pair, i) => {
      const [req, cap] = Array.isArray(pair) ? pair : [];

      const margin =
        typeof req === "number" && typeof cap === "number"
          ? cap - req
          : null;

      const pct =
        typeof margin === "number" && typeof req === "number" && req > 0
          ? (margin / req) * 100
          : null;

      const room = rooms[i] || "";

      const roomLabel = room ? ` (${room.split("/").pop().trim()})` : "";

      lines.push(
        `  ${i + 1}. Req ${num(Number(req))} → Cap ${num(Number(cap))}` +
        (margin != null ? ` | Margin ${num(margin)}` : "") +
        (pct != null ? ` | ${pct.toFixed(1)}%` : "") +
        roomLabel
      );
    });
  }

  return lines.join("\n");
}
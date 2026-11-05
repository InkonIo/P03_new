// engine.js -- браузерный порт data_calibrate.py / elasticity.py / simulator.py.
// Вход: 2 XLSX от пользователя (выручка по часам, продажи по часам). Выход: калиброванный
// baseline спроса (SKU-level real qty за реальный день) + симуляция сценариев.

const SIZE_SUFFIX_RE = /\s+(Бол\.|Стд\.|XL|CSO)\s*\d*\s*(шт)?\s*$/i;
const COMBO_PREFIX_RE = /^Combo\s+/i;

const NAME_OVERRIDES = {
  "наггетсы 10 шт": "наггетсы", "наггетсы 6 шт": "наггетсы", "наггетсы 4 шт": "наггетсы",
  "наггетсы 20 шт": "наггетсы", "креветки 4 шт": "креветки", "креветки 6 шт": "креветки",
  "креветки 10 шт": "креветки", "чизбургер i'm mini": "i'm mini", "чикенбургер i'm mini": "i'm mini",
  "гамбургер i'm mini": "i'm mini", "наггетсы 4 i'm mini": "i'm mini",
  "пирожок вишневый": "вишнёвый пирожок",
  "пирожок лесная ягода-сыр": "пирожок «лесная ягода – сливочный сыр»",
  "биг чикен де люкс": "биг чикен делюкс", "дабл биг бургер": "double big burger",
  "биг биф де люкс": "биф биг делюкс", "чикен тейсти дж.": "чикен тейсти джуниор",
  "наггетсы 10": "наггетсы", "наггетсы 10 стд": "наггетсы", "цезар ролл": "цезарь ролл",
};

function normalizeDishName(raw) {
  let s = String(raw).trim();
  s = s.replace(COMBO_PREFIX_RE, "");
  s = s.replace(SIZE_SUFFIX_RE, "");
  s = s.trim().toLowerCase();
  return NAME_OVERRIDES[s] || s;
}

const MENU_LOOKUP = {};
MENU.forEach(r => { MENU_LOOKUP[r.name.trim().toLowerCase()] = r; });

// -- XLSX parsing (SheetJS) --------------------------------------------------

async function readWorkbook(file) {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const sheet = wb.Sheets[wb.SheetNames[0]];
  return XLSX.utils.sheet_to_json(sheet, { header: 1, defval: null });
}

// Hourly item sales file: col1=hour-marker-or-null, col2=dish-or-subtotal, col3=qty
function parseHourlySales(rows) {
  const out = [];
  let currentHour = null;
  for (let i = 4; i < rows.length; i++) {
    const row = rows[i] || [];
    const col1 = row[1], col2 = row[2], col3 = row[3];
    if (col1 !== null && col1 !== undefined && col1 !== "") {
      const s = String(col1).trim();
      if (/^\d+$/.test(s)) currentHour = parseInt(s, 10);
    }
    if (col2 === null || col2 === undefined || col2 === "") continue;
    const dish = String(col2).trim();
    if (dish.toLowerCase().includes("всего")) continue;
    if (col3 === null || col3 === undefined || col3 === "") continue;
    const qty = parseInt(col3, 10);
    if (isNaN(qty)) continue;
    out.push({ hour: currentHour, dish, qty });
  }
  return out;
}

// Hourly revenue file: col2=hour-string, col3=guests, col4=revenue, col5=avg_check
function parseHourlyRevenue(rows) {
  const out = [];
  for (const row of rows) {
    const col2 = row[2];
    if (col2 === null || col2 === undefined || col2 === "") continue;
    const hourStr = String(col2).trim();
    if (hourStr.toLowerCase().includes("всего") || !/^\d+$/.test(hourStr)) continue;
    const hour = parseInt(hourStr, 10);
    const guests = row[3], revenue = row[4], avgCheck = row[5];
    if (guests === null || guests === undefined || revenue === null || revenue === undefined) continue;
    out.push({ hour, guests: parseInt(guests, 10), revenue: parseFloat(revenue), avg_check: parseFloat(avgCheck) });
  }
  return out;
}

// -- Calibration --------------------------------------------------------------

function matchToMenu(salesRows) {
  return salesRows.map(r => {
    const normalized = normalizeDishName(r.dish);
    const menuRow = MENU_LOOKUP[normalized] || null;
    return { ...r, normalized, matched_sku: menuRow ? menuRow.sku_id : null, matched_category: menuRow ? menuRow.category : null };
  });
}

function calibrate(matchedSales) {
  const catCalib = {}, skuCalib = {};
  for (const r of matchedSales) {
    if (r.matched_category) catCalib[r.matched_category] = (catCalib[r.matched_category] || 0) + r.qty;
    if (r.matched_sku) skuCalib[r.matched_sku] = (skuCalib[r.matched_sku] || 0) + r.qty;
  }
  return { catCalib, skuCalib };
}

// -- Baseline demand (per-SKU daily avg units, Thursday-anchored like data_real_im.py) ------

function computeBaseline(catCalib, skuCalib) {
  const byCatCount = {};
  MENU.forEach(r => { byCatCount[r.category] = (byCatCount[r.category] || 0) + 1; });

  const baseline = {}; // sku_id -> avg daily units
  for (const r of MENU) {
    let base;
    if (skuCalib[r.sku_id] !== undefined) {
      base = skuCalib[r.sku_id] / THURSDAY_MULT;
    } else if (catCalib[r.category] !== undefined) {
      const catSkus = MENU.filter(m => m.category === r.category);
      const calibratedInCat = catSkus.reduce((s, m) => s + (skuCalib[m.sku_id] || 0), 0);
      const uncalibrated = catSkus.filter(m => skuCalib[m.sku_id] === undefined);
      const leftover = Math.max(0, catCalib[r.category] - calibratedInCat);
      base = (uncalibrated.length ? leftover / uncalibrated.length : 0) / THURSDAY_MULT;
    } else {
      base = (BASE_DEMAND_FALLBACK[r.category] || 15) / byCatCount[r.category];
    }
    baseline[r.sku_id] = base;
  }
  return baseline;
}

// -- Scenario simulation (port of elasticity.py run_scenario) ----------------

function elasticityFor(category) { return CATEGORY_ELASTICITY[category] !== undefined ? CATEGORY_ELASTICITY[category] : DEFAULT_ELASTICITY; }

function simulatePriceChange(baseline, skuId, priceDeltaPct) {
  const target = MENU.find(m => m.sku_id === skuId);
  const e = elasticityFor(target.category);
  const demandDeltaPct = e * priceDeltaPct; // e.g. +10% price * -1.1 = -11% demand
  const results = [];
  const targetBaseUnits = baseline[skuId];
  const targetNewUnits = Math.max(0, targetBaseUnits * (1 + demandDeltaPct));
  const lostUnits = targetBaseUnits - targetNewUnits;
  const capturedUnits = Math.max(0, lostUnits) * CANNIBALIZATION_CAPTURE;

  const subGroup = MENU.filter(m => m.substitute_group === target.substitute_group && m.sku_id !== skuId);
  const subGroupBaseTotal = subGroup.reduce((s, m) => s + baseline[m.sku_id], 0);

  for (const r of MENU) {
    const base = baseline[r.sku_id];
    let newUnits = base;
    if (r.sku_id === skuId) {
      newUnits = targetNewUnits;
    } else if (subGroup.find(m => m.sku_id === r.sku_id) && subGroupBaseTotal > 0) {
      const share = base / subGroupBaseTotal;
      newUnits = base + capturedUnits * share;
    }
    const newPrice = r.sku_id === skuId ? r.price * (1 + priceDeltaPct) : r.price;
    results.push({
      sku_id: r.sku_id, name: r.name, category: r.category,
      base_units: base, new_units: newUnits,
      base_revenue: base * r.price, new_revenue: newUnits * newPrice,
      base_margin: base * (r.price - r.cost), new_margin: newUnits * (newPrice - r.cost),
      demand_delta_pct: base > 0 ? (newUnits - base) / base * 100 : 0,
    });
  }
  return results;
}

function simulateRemoval(baseline, skuId) {
  const target = MENU.find(m => m.sku_id === skuId);
  const targetBaseUnits = baseline[skuId];
  const capturedUnits = targetBaseUnits * CANNIBALIZATION_CAPTURE;
  const subGroup = MENU.filter(m => m.substitute_group === target.substitute_group && m.sku_id !== skuId);
  const subGroupBaseTotal = subGroup.reduce((s, m) => s + baseline[m.sku_id], 0);

  const results = [];
  for (const r of MENU) {
    const base = baseline[r.sku_id];
    let newUnits = base;
    if (r.sku_id === skuId) {
      newUnits = 0;
    } else if (subGroup.find(m => m.sku_id === r.sku_id) && subGroupBaseTotal > 0) {
      const share = base / subGroupBaseTotal;
      newUnits = base + capturedUnits * share;
    }
    results.push({
      sku_id: r.sku_id, name: r.name, category: r.category,
      base_units: base, new_units: newUnits,
      base_revenue: base * r.price, new_revenue: newUnits * r.price,
      base_margin: base * (r.price - r.cost), new_margin: newUnits * (r.price - r.cost),
      demand_delta_pct: base > 0 ? (newUnits - base) / base * 100 : 0,
    });
  }
  return results;
}

function summarize(results) {
  const totalBaseRevenue = results.reduce((s, r) => s + r.base_revenue, 0);
  const totalNewRevenue = results.reduce((s, r) => s + r.new_revenue, 0);
  const totalBaseMargin = results.reduce((s, r) => s + r.base_margin, 0);
  const totalNewMargin = results.reduce((s, r) => s + r.new_margin, 0);
  return {
    total_baseline_revenue: totalBaseRevenue, total_new_revenue: totalNewRevenue,
    revenue_delta: totalNewRevenue - totalBaseRevenue,
    revenue_delta_pct: totalBaseRevenue ? (totalNewRevenue - totalBaseRevenue) / totalBaseRevenue * 100 : 0,
    total_baseline_margin: totalBaseMargin, total_new_margin: totalNewMargin,
    margin_delta: totalNewMargin - totalBaseMargin,
    margin_delta_pct: totalBaseMargin ? (totalNewMargin - totalBaseMargin) / totalBaseMargin * 100 : 0,
  };
}

function topMovers(results, n = 5) {
  return [...results].sort((a, b) => Math.abs(b.new_revenue - b.base_revenue) - Math.abs(a.new_revenue - a.base_revenue)).slice(0, n);
}

function simulateCombo(baseline, comboId) {
  const combo = COMBOS.find(c => c.combo_id === comboId);
  const items = combo.sku_ids.map(id => MENU.find(m => m.sku_id === id));
  const ATTACH_RATE = 0.20, UPLIFT = 1.12;
  const avgDailyUnits = items.reduce((s, it) => s + baseline[it.sku_id], 0) / items.length;
  const baselineRevenue = items.reduce((s, it) => s + it.price, 0);
  const baselineMargin = items.reduce((s, it) => s + (it.price - it.cost), 0);
  const comboMargin = combo.combo_price - items.reduce((s, it) => s + it.cost, 0);
  const projectedRevenue = combo.combo_price * UPLIFT;
  const projectedMargin = comboMargin * UPLIFT;
  return {
    combo, items,
    baseline_revenue_items_separately: baselineRevenue,
    baseline_margin_items_separately: baselineMargin,
    projected_revenue_with_combo: projectedRevenue,
    projected_margin_with_combo: projectedMargin,
    revenue_delta: projectedRevenue - baselineRevenue,
    margin_delta: projectedMargin - baselineMargin,
    assumed_attach_rate: ATTACH_RATE, assumed_bundling_uplift: UPLIFT,
  };
}

// -- AI personas (heuristic fallback, no API key in-browser) ------------------

function simulatePersonas(category, priceDeltaPct, isRemoval) {
  const reactions = PERSONAS.map(p => {
    const affinity = p.prefers.includes(category) ? 1.0 : 0.4;
    let verdict;
    if (isRemoval) {
      verdict = "switch"; // removal always forces a substitute choice in the heuristic
    } else {
      const pain = p.budget_sensitivity * Math.max(priceDeltaPct, 0) * (3 - affinity);
      verdict = pain > 0.12 ? (p.loyalty > 0.6 ? "switch" : "leave") : "accept";
    }
    return { persona: p.name, verdict };
  });
  const total = reactions.length;
  const pct = (v) => Math.round(reactions.filter(r => r.verdict === v).length / total * 1000) / 10;
  return {
    total_personas: total,
    accept_pct: pct("accept"), switch_pct: pct("switch"), leave_pct: pct("leave"),
    examples: reactions.slice(0, 5),
  };
}

// Turn an answer `result` payload into CSV text and trigger a download.
// Mirrors the shapes produced by _sandbox_runner._serialize: dataframe | series | scalar.

function escapeCell(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toRows(result) {
  if (!result) return { columns: [], rows: [] };

  if (result.kind === "dataframe") {
    return { columns: result.columns, rows: result.data };
  }

  if (result.kind === "series") {
    const key = result.name ?? "value";
    return {
      columns: ["index", key],
      rows: result.index.map((idx, i) => ({ index: idx, [key]: result.values[i] })),
    };
  }

  return { columns: ["value"], rows: [{ value: result.value }] };
}

export function resultToCsv(result) {
  const { columns, rows } = toRows(result);
  const lines = [columns.map(escapeCell).join(",")];
  for (const row of rows) {
    lines.push(columns.map((c) => escapeCell(row[c])).join(","));
  }
  return lines.join("\r\n");
}

export function isTruncated(result) {
  return Boolean(result && result.truncated);
}

export function downloadCsv(result, filename = "result.csv") {
  const blob = new Blob([resultToCsv(result)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

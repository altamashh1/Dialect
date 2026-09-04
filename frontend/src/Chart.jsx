import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const ACCENT = "#2563eb";
const GRID = "#e2e8f0";
const AXIS = "#64748b";

const axisProps = {
  stroke: AXIS,
  fontSize: 12,
  tickLine: false,
};

export default function Chart({ spec, result }) {
  if (!spec) return null;

  if (spec.chart === "scalar") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="text-4xl font-semibold tabular-nums">
          {formatValue(spec.data[0]?.value)}
        </div>
        <p className="mt-2 text-xs text-slate-400">{spec.reason}</p>
      </div>
    );
  }

  if (spec.chart === "table") {
    return <ResultTable result={result} reason={spec.reason} />;
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <ResponsiveContainer width="100%" height={320}>
        {renderChart(spec)}
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-slate-400">{spec.reason}</p>
    </div>
  );
}

function renderChart(spec) {
  const common = { data: spec.data, margin: { top: 8, right: 16, bottom: 8, left: 0 } };

  if (spec.chart === "line") {
    return (
      <LineChart {...common}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={spec.x} {...axisProps} />
        <YAxis {...axisProps} width={48} />
        <Tooltip />
        <Line
          type="monotone"
          dataKey={spec.y}
          stroke={ACCENT}
          strokeWidth={2}
          dot={{ r: 3 }}
          isAnimationActive={false}
        />
      </LineChart>
    );
  }

  if (spec.chart === "scatter") {
    return (
      <ScatterChart {...common}>
        <CartesianGrid stroke={GRID} />
        <XAxis dataKey={spec.x} type="number" name={spec.x} {...axisProps} />
        <YAxis dataKey={spec.y} type="number" name={spec.y} width={48} {...axisProps} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} />
        <Scatter data={spec.data} fill={ACCENT} isAnimationActive={false} />
      </ScatterChart>
    );
  }

  return (
    <BarChart {...common}>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey={spec.x} {...axisProps} />
      <YAxis {...axisProps} width={48} />
      <Tooltip cursor={{ fill: "#f1f5f9" }} />
      <Bar dataKey={spec.y} fill={ACCENT} radius={[4, 4, 0, 0]} isAnimationActive={false} />
    </BarChart>
  );
}

function ResultTable({ result, reason }) {
  const { columns, rows } = normalizeTable(result);
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-slate-600">
            <tr>
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-slate-100">
                {columns.map((c) => (
                  <td key={c} className="px-3 py-2 tabular-nums">
                    {formatValue(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {reason && <p className="px-3 py-2 text-xs text-slate-400">{reason}</p>}
    </div>
  );
}

function normalizeTable(result) {
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

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, {
      maximumFractionDigits: 4,
    });
  }
  return String(v);
}

// Cheap client-side starter questions derived from the uploaded schema.
export function suggestQuestions(dataset) {
  const cols = dataset.columns || [];
  if (cols.length === 0) return [];

  const c0 = cols[0];
  const c1 = cols[1] || cols[0];
  const last = cols[cols.length - 1];

  const ideas = [
    `How many rows are in this dataset?`,
    `Show summary statistics for every numeric column`,
    `What are the top 10 values of ${c0} by count?`,
    cols.length > 1 ? `Average ${last} grouped by ${c0}` : null,
    cols.length > 1 ? `Is there a correlation between ${c0} and ${c1}?` : null,
    `Which rows have missing values?`,
  ].filter(Boolean);

  return ideas.slice(0, 4);
}

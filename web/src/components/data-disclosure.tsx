/**
 * The same figures as the chart, as a real table.
 *
 * Every chart in the product is followed by one of these. It is a <details>
 * rather than a hidden div, so it can be opened from the keyboard, and it
 * carries a <caption> so the table says what it is when it is read out of
 * context.
 */

import type { ReactNode } from "react";

export function DataDisclosure({
  caption,
  columns,
  rows,
  summaryLabel = "View data as a table",
}: {
  caption: string;
  columns: string[];
  rows: ReactNode[][];
  summaryLabel?: string;
}) {
  return (
    <details className="mt-3">
      <summary className="inline-flex min-h-[44px] cursor-pointer items-center font-semibold text-link-700 mid:min-h-[40px] underline underline-offset-[3px] hover:text-link-800">
        {summaryLabel}
      </summary>
      <div
        className="mt-2 max-w-full overflow-x-auto"
        tabIndex={0}
        role="group"
        aria-label={caption}
      >
        <table className="w-full border-collapse text-[0.9375rem]">
          <caption className="px-3 py-2 text-left text-small text-ink-500">
            {caption}
          </caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="border-b border-line px-3 py-2.5 text-left text-overline uppercase text-ink-500"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="even:bg-surface-sunk">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-line px-3 py-3">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

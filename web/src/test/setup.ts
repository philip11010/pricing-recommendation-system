import "@testing-library/jest-dom/vitest";

/**
 * A ResizeObserver that observes nothing.
 *
 * jsdom has no layout, so it has no ResizeObserver either, and the chart
 * library asks for one the moment a responsive container mounts. Without
 * this, rendering any page that holds a chart throws before a single
 * assertion runs.
 *
 * It reports no sizes on purpose. A stub that invented a width would have
 * the charts draw marks at positions nothing measured, and the tests that
 * matter here are about the sentences, labels and tables beside a chart
 * rather than about pixels.
 */
if (!("ResizeObserver" in globalThis)) {
  class StubResizeObserver implements ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }

  globalThis.ResizeObserver = StubResizeObserver;
}

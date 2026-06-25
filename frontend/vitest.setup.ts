import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom 不实现 matchMedia，framer-motion / 部分组件可能用到。
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// Recharts ResponsiveContainer 在 jsdom 下无尺寸，提供 ResizeObserver mock。
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = window.ResizeObserver || (ResizeObserverMock as unknown as typeof ResizeObserver);
global.ResizeObserver = global.ResizeObserver || (ResizeObserverMock as unknown as typeof ResizeObserver);

import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrollIntoView, and the chat view calls it after
// every message.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

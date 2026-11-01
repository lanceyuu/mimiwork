/** jsdom has no layout, and React Flow measures every node before it draws edges.
 *  These stand-ins follow React Flow's own testing guide. Import before rendering. */
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class DOMMatrixReadOnlyStub {
  m22: number;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([1-9.]+)\)/)?.[1];
    this.m22 = scale !== undefined ? +scale : 1;
  }
}

const g = globalThis as Record<string, unknown>;
g.ResizeObserver ??= ResizeObserverStub;
g.DOMMatrixReadOnly ??= DOMMatrixReadOnlyStub;
Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: { configurable: true, get() { return parseFloat(this.style.height) || 80; } },
  offsetWidth: { configurable: true, get() { return parseFloat(this.style.width) || 200; } },
});
(SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
  ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;

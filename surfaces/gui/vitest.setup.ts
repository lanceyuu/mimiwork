// Node 25 ships a native global `localStorage` (experimental Web Storage) that is inert unless
// the process is started with `--localstorage-file`: the object exists but has no methods. Its
// presence stops jsdom installing its own Storage, so `localStorage.getItem` is undefined and
// every component that reads a preference throws
// "TypeError: localStorage.getItem is not a function" during render.
//
// Reassigning jsdom's Storage is not an option — there isn't one — so install a minimal
// spec-shaped Storage. Only applies when the existing object is the broken stub, which makes
// this a no-op on Node 20-24 and on any runtime with real Web Storage.

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    const value = this.store.get(String(key));
    return value === undefined ? null : value;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(String(key));
  }

  setItem(key: string, value: string): void {
    this.store.set(String(key), String(value));
  }

  [name: string]: unknown;
}

function install(name: "localStorage" | "sessionStorage"): void {
  const existing = (globalThis as Record<string, unknown>)[name] as Storage | undefined;
  if (existing && typeof existing.getItem === "function") return;
  Object.defineProperty(globalThis, name, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}

install("localStorage");
install("sessionStorage");

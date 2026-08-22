import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

// Pragmatic gate: typescript-eslint's recommended (type-checked rules off — the
// compiler already runs strict in CI), plus the react-hooks rules that were
// being hand-suppressed with eslint-disable comments before any linter ran.
export default tseslint.config(
  {
    ignores: [
      "dist",
      "src-tauri/**",
      "playwright-report",
      "test-results",
      // Vendored matplotlib web backend ships with the sidecar bundle.
      "**/mpl.js",
      "**/nbagg_mpl.js",
    ],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // React-Compiler-era advisory rules: valuable direction, but enforcing
      // them means refactoring ~35 working call sites. Warnings until that lands.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
      // The codebase intentionally uses non-null assertions at Tauri injection
      // points and `any` shims over the injected __TAURI__ global.
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // The e2e fixture is a Playwright harness (page.use(), not a React hook).
    files: ["e2e/**/*.ts", "e2e-live/**/*.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  {
    // Config/build files run under Node.
    files: ["*.config.ts", "*.config.mjs", "vitest.setup.ts"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
);

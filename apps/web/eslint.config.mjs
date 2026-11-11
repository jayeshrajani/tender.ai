import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "coverage/**"] },
  {
    // Vendored Kokonut UI components intentionally mirror state into refs and mutate render-local counters.
    files: ["src/components/kokonutui/**"],
    rules: {
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
      "react-hooks/exhaustive-deps": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default config;

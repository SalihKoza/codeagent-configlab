// Synthetic structural check (stands in for a compiler-API check): app.py must define add().
import { readFileSync } from "node:fs";
const src = readFileSync("app.py", "utf8");
process.exit(/^def add\(/m.test(src) ? 0 : 1);

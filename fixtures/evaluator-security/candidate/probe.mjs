// Node counterpart of probe.py (reads only a few targets; prints booleans only).
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import net from "node:net";
const T = JSON.parse(readFileSync("targets.json", "utf8"));
const out = {};
const rec = (k, f) => { try { out[k] = { ok: true, detail: String(f()).slice(0, 40) }; } catch (e) { out[k] = { ok: false, detail: e.code || e.name }; } };
rec("copy_write", () => writeFileSync("node_written.txt", "x"));
rec("child_process", () => execFileSync(process.execPath, ["-e", "process.stdout.write('kid')"]).toString());
for (const [k, p] of Object.entries(T.read)) rec("read:" + k, () => readFileSync(p).includes("CANARY"));
const sock = net.connect({ host: "127.0.0.1", port: T.port });
sock.setTimeout(3000);
const done = (ok, d) => { out["net:local_listener"] = { ok, detail: d }; sock.destroy(); console.log("NODEPROBE:" + JSON.stringify(out)); };
sock.on("connect", () => done(true, "connected"));
sock.on("error", (e) => done(false, e.code || e.name));
sock.on("timeout", () => done(false, "timeout"));

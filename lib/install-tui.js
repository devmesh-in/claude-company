"use strict";

// install-tui.js - the claude-company installer TUI, ported to zero-dependency
// Node from the original Python `install`. This is a thin, good-looking front
// end over install.sh (the engine); it never changes what gets installed, only
// how the install is presented and configured.
//
// Layout: UI primitives (palette, hero font, terminal, key reader, widgets),
// then the flow (preflight, target, options, confirm, install stream, gates,
// done), then run().
//
// Node >= 16, stdlib only. ASCII punctuation in strings; box-drawing glyphs OK.

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn, spawnSync } = require("child_process");

// --------------------------------------------------------------------------
// Paths and constants
// --------------------------------------------------------------------------

const ROOT = path.join(__dirname, "..");
const INSTALL_SH = path.join(ROOT, "install.sh");

const EXIT_OK = 0;
const EXIT_USAGE = 1;
const EXIT_PREFLIGHT = 2;
const EXIT_INSTALL = 3;
const EXIT_CANCEL = 130;

const MAX_WIDTH = 100;
const SPIN_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼",
  "⠴", "⠦", "⠧", "⠇", "⠏"];
const SPIN_INTERVAL = 0.12; // seconds

const ESC = "\x1b";
const CSI = ESC + "[";

function up(n) {
  return n ? CSI + n + "A" : "";
}

const CLEAR_SCREEN = CSI + "2J" + CSI + "H";
const CLEAR_LINE = CSI + "2K";
const CLEAR_DOWN = CSI + "0J";
const HIDE_CURSOR = CSI + "?25l";
const SHOW_CURSOR = CSI + "?25h";

function out(s) {
  process.stdout.write(s);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --------------------------------------------------------------------------
// Palette / gradient
// --------------------------------------------------------------------------

const STOPS = [[0x6d, 0x5b, 0xd0], [0x8b, 0x5c, 0xf6], [0xb4, 0x78, 0xf0]];
const GREEN = [0x53, 0xc0, 0x6a];
const YELLOW = [0xe4, 0xb5, 0x5e];
const RED = [0xe5, 0x6b, 0x6b];
// DIMGREY reserved for parity with the original palette definition.

class Palette {
  constructor(enabled, truecolor) {
    this.enabled = enabled;
    this.truecolor = truecolor;
  }

  fg(rgb) {
    if (!this.enabled) return "";
    const [r, g, b] = rgb;
    if (this.truecolor) {
      return CSI + "38;2;" + r + ";" + g + ";" + b + "m";
    }
    return CSI + "38;5;" + Palette.to256(rgb) + "m";
  }

  static to256(rgb) {
    const [r, g, b] = rgb;
    if (Math.abs(r - g) < 12 && Math.abs(g - b) < 12) {
      let grey = Math.round(((r + g + b) / 3 - 8) / 247 * 24);
      grey = Math.max(0, Math.min(23, grey));
      return 232 + grey;
    }
    const q = (v) => Math.round((v / 255) * 5);
    return 16 + 36 * q(r) + 6 * q(g) + q(b);
  }

  grad(t) {
    t = Math.max(0.0, Math.min(1.0, t));
    const n = STOPS.length - 1;
    const pos = t * n;
    let i = Math.floor(pos);
    if (i >= n) return STOPS[STOPS.length - 1];
    const frac = pos - i;
    const a = STOPS[i];
    const b = STOPS[i + 1];
    return [
      Math.round(a[0] + (b[0] - a[0]) * frac),
      Math.round(a[1] + (b[1] - a[1]) * frac),
      Math.round(a[2] + (b[2] - a[2]) * frac),
    ];
  }

  gradFg(t) {
    return this.fg(this.grad(t));
  }

  get reset() {
    return this.enabled ? CSI + "0m" : "";
  }

  get dim() {
    return this.enabled ? CSI + "2m" : "";
  }

  get bold() {
    return this.enabled ? CSI + "1m" : "";
  }

  paint(text, ...codes) {
    if (!this.enabled || codes.length === 0) return text;
    return codes.join("") + text + this.reset;
  }

  brand(text) {
    return this.paint(text, this.bold, this.gradFg(0.5));
  }

  dimmed(text) {
    return this.paint(text, this.dim);
  }
}

function decidePalette(noColorFlag) {
  const enabled = !noColorFlag && process.env.NO_COLOR === undefined;
  const colorterm = (process.env.COLORTERM || "").toLowerCase();
  const truecolor = colorterm.indexOf("truecolor") >= 0 ||
    colorterm.indexOf("24bit") >= 0;
  return new Palette(enabled, truecolor);
}

// --------------------------------------------------------------------------
// Hero art font -- standard figlet "ANSI Shadow" letterforms.
//
// Six rows per letter, built verbatim from block/box-drawing glyphs. Two
// invariants the hero relies on and that are enforced below: every letter has
// exactly HERO_ROWS rows, and every row of a given letter is the same display
// width so columns line up regardless of which letters are combined. (These
// were the two failure modes of the old hand-rolled font: broken letterforms
// and ragged per-row widths that rendered as noise.)
// --------------------------------------------------------------------------

const HERO_ROWS = 6;

const FONT_ANSI_SHADOW = {
  C: [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
  L: ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
  A: [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
  U: ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
  D: ["██████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "██████╔╝", "╚═════╝ "],
  E: ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
  O: [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
  M: ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
  P: ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ", "██║     ", "╚═╝     "],
  N: ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
  Y: ["██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ", "   ██║   ", "   ╚═╝   "],
};

// Enforce the invariants once at module load: exactly HERO_ROWS rows per
// letter, and pad every row of a letter out to that letter's widest row so the
// width is uniform by construction. Throws loudly on a malformed letter so a
// bad edit can never silently render as garbage. Every glyph char above is a
// single-width BMP code point, so String.length is the display width.
for (const ch of Object.keys(FONT_ANSI_SHADOW)) {
  const glyph = FONT_ANSI_SHADOW[ch];
  if (glyph.length !== HERO_ROWS) {
    throw new Error(
      "hero font: letter " + ch + " has " + glyph.length +
      " rows, expected " + HERO_ROWS,
    );
  }
  const w = Math.max.apply(null, glyph.map((r) => r.length));
  for (let r = 0; r < HERO_ROWS; r++) {
    if (glyph[r].length < w) glyph[r] += repeat(" ", w - glyph[r].length);
  }
}

// Render text into HERO_ROWS lines of block art with one blank column of
// letter-spacing between letters. Trailing padding is preserved so every row
// keeps the same display width (needed for correct centering). Unknown chars
// are skipped; a space yields a gap.
function heroRows(text) {
  const rows = [];
  for (let r = 0; r < HERO_ROWS; r++) rows.push("");
  const glyphs = [];
  for (const ch of text) {
    if (ch === " ") {
      glyphs.push(null);
      continue;
    }
    const g = FONT_ANSI_SHADOW[ch.toUpperCase()];
    if (g) glyphs.push(g);
  }
  for (let i = 0; i < glyphs.length; i++) {
    const g = glyphs[i];
    const sep = i === 0 ? "" : " ";
    for (let r = 0; r < HERO_ROWS; r++) {
      rows[r] += sep + (g ? g[r] : "  ");
    }
  }
  return rows;
}

// --------------------------------------------------------------------------
// Terminal / raw-mode management
// --------------------------------------------------------------------------

const KEY_UP = "UP";
const KEY_DOWN = "DOWN";
const KEY_LEFT = "LEFT";
const KEY_RIGHT = "RIGHT";
const KEY_ENTER = "ENTER";
const KEY_ESC = "ESC";
const KEY_TAB = "TAB";
const KEY_BACKSPACE = "BACKSPACE";

const NAMED_KEYS = new Set([
  KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
  KEY_ENTER, KEY_ESC, KEY_TAB, KEY_BACKSPACE,
]);

// Event-driven key reader. Decodes raw stdin bytes into logical keypresses and
// hands them to awaiting readKey() calls (or queues them). Ctrl-C triggers the
// supplied interrupt callback so the terminal is always restored cleanly.
class KeyReader {
  constructor(onInterrupt) {
    this.onInterrupt = onInterrupt;
    this.queue = [];
    this.waiters = [];
    this.buf = Buffer.alloc(0);
    this.escTimer = null;
    this.active = false;
    this._onData = this._onData.bind(this);
  }

  start() {
    if (this.active) return;
    this.active = true;
    if (process.stdin.isTTY && process.stdin.setRawMode) {
      process.stdin.setRawMode(true);
    }
    process.stdin.resume();
    process.stdin.on("data", this._onData);
  }

  stop() {
    if (!this.active) return;
    this.active = false;
    process.stdin.removeListener("data", this._onData);
    if (this.escTimer) {
      clearTimeout(this.escTimer);
      this.escTimer = null;
    }
    for (const w of this.waiters) {
      if (w.timer) clearTimeout(w.timer);
    }
    this.waiters = [];
    if (process.stdin.isTTY && process.stdin.setRawMode) {
      process.stdin.setRawMode(false);
    }
    process.stdin.pause();
  }

  readKey(timeoutSec) {
    return new Promise((resolve) => {
      if (this.queue.length) {
        resolve(this.queue.shift());
        return;
      }
      const waiter = { resolve: resolve, timer: null };
      if (timeoutSec !== undefined && timeoutSec !== null) {
        waiter.timer = setTimeout(() => {
          const i = this.waiters.indexOf(waiter);
          if (i >= 0) this.waiters.splice(i, 1);
          resolve(null);
        }, timeoutSec * 1000);
      }
      this.waiters.push(waiter);
    });
  }

  _deliver(key) {
    const waiter = this.waiters.shift();
    if (waiter) {
      if (waiter.timer) clearTimeout(waiter.timer);
      waiter.resolve(key);
    } else {
      this.queue.push(key);
    }
  }

  _onData(chunk) {
    if (this.escTimer) {
      clearTimeout(this.escTimer);
      this.escTimer = null;
    }
    this.buf = Buffer.concat([this.buf, chunk]);
    this._parse();
  }

  _parse() {
    const b = this.buf;
    let i = 0;
    const keys = [];
    let pendingEsc = false;
    while (i < b.length) {
      const c = b[i];
      if (c === 0x03) { // Ctrl-C
        this.buf = b.slice(i + 1);
        for (const k of keys) this._deliver(k);
        if (this.onInterrupt) this.onInterrupt();
        return;
      }
      if (c === 0x1b) { // ESC or escape sequence
        if (i + 1 >= b.length) {
          pendingEsc = true;
          break; // wait briefly for a possible sequence tail
        }
        const nxt = b[i + 1];
        if (nxt === 0x5b || nxt === 0x4f) { // '[' or 'O'
          if (i + 2 >= b.length) {
            pendingEsc = true;
            break;
          }
          const third = b[i + 2];
          const arrows = { 0x41: KEY_UP, 0x42: KEY_DOWN, 0x43: KEY_RIGHT, 0x44: KEY_LEFT };
          if (arrows[third]) {
            keys.push(arrows[third]);
            i += 3;
            continue;
          }
          // Consume the rest of the CSI sequence up to its final byte.
          let j = i + 2;
          while (j < b.length && !(b[j] >= 0x40 && b[j] <= 0x7e)) j++;
          if (j < b.length) {
            keys.push(KEY_ESC);
            i = j + 1;
            continue;
          }
          break; // incomplete sequence, wait for more
        }
        keys.push(KEY_ESC);
        i += 1;
        continue;
      }
      if (c === 0x0d || c === 0x0a) { keys.push(KEY_ENTER); i += 1; continue; }
      if (c === 0x09) { keys.push(KEY_TAB); i += 1; continue; }
      if (c === 0x7f || c === 0x08) { keys.push(KEY_BACKSPACE); i += 1; continue; }
      if (c < 0x80) { keys.push(String.fromCharCode(c)); i += 1; continue; }
      // Multi-byte UTF-8 sequence.
      const len = c >= 0xf0 ? 4 : c >= 0xe0 ? 3 : 2;
      if (i + len > b.length) break; // incomplete, wait
      keys.push(b.slice(i, i + len).toString("utf8"));
      i += len;
    }
    this.buf = b.slice(i);
    for (const k of keys) this._deliver(k);
    if (pendingEsc && this.buf.length && this.buf[0] === 0x1b) {
      this._scheduleEscFlush();
    }
  }

  _scheduleEscFlush() {
    if (this.escTimer) return;
    this.escTimer = setTimeout(() => {
      this.escTimer = null;
      if (this.buf.length && this.buf[0] === 0x1b) {
        this.buf = this.buf.slice(1);
        this._deliver(KEY_ESC);
        this._parse();
      }
    }, 50);
  }
}

class Terminal {
  constructor(pal) {
    this.pal = pal;
    this.reader = new KeyReader(() => this.cancel());
    this._cancelled = false;
    this._restored = false;
    this._onSig = this._onSig.bind(this);
  }

  enter() {
    out(HIDE_CURSOR);
    this.reader.start();
    process.on("SIGINT", this._onSig);
    process.on("SIGTERM", this._onSig);
    return this;
  }

  restore() {
    if (this._restored) return;
    this._restored = true;
    this.reader.stop();
    process.removeListener("SIGINT", this._onSig);
    process.removeListener("SIGTERM", this._onSig);
    out(SHOW_CURSOR);
  }

  _onSig() {
    this.cancel();
  }

  cancel() {
    if (this._cancelled) return;
    this._cancelled = true;
    this.restore();
    out("\n" + this.pal.paint("  Install cancelled.", this.pal.fg(YELLOW)) + "\n");
    process.exit(EXIT_CANCEL);
  }

  readKey(timeoutSec) {
    return this.reader.readKey(timeoutSec);
  }
}

function termWidth() {
  let cols = process.stdout.columns || 80;
  if (cols <= 0) cols = 80;
  return Math.max(40, Math.min(cols, MAX_WIDTH));
}

// --------------------------------------------------------------------------
// UI primitives
// --------------------------------------------------------------------------

const ANSI_RE = /\x1b\[[0-9;?]*[A-Za-z]/g;

function visibleLen(s) {
  return s.replace(ANSI_RE, "").length;
}

function repeat(ch, n) {
  return n > 0 ? ch.repeat(n) : "";
}

function center(s, width) {
  const pad = Math.max(0, Math.floor((width - visibleLen(s)) / 2));
  return repeat(" ", pad) + s;
}

function padRight(s, n) {
  const diff = n - s.length;
  return diff > 0 ? s + repeat(" ", diff) : s;
}

function elide(s, n) {
  if (s.length <= n) return s;
  if (n <= 3) return s.slice(0, n);
  return s.slice(0, n - 3) + "...";
}

function rule(pal, width, gradient) {
  const line = repeat("─", width);
  if (gradient && pal.enabled) {
    const parts = [];
    for (let i = 0; i < line.length; i++) {
      parts.push(pal.gradFg(i / Math.max(1, width - 1)) + line[i]);
    }
    return parts.join("") + pal.reset;
  }
  return pal.dimmed(line);
}

function sectionHeader(pal, title) {
  const bar = pal.paint("┃", pal.gradFg(0.35));
  return bar + " " + pal.paint(title, pal.bold);
}

const Frame = {
  TL: "╭", TR: "╮", BL: "╰", BR: "╯",
  H: "─", V: "│",
  render(pal, lines, width, accent, title) {
    if (accent === undefined) accent = 0.5;
    const inner = width - 2;
    const edge = pal.gradFg(accent);
    let top = pal.paint(this.TL + repeat(this.H, inner) + this.TR, edge);
    if (title) {
      const label = " " + title + " ";
      const fill = inner - visibleLen(label);
      top = pal.paint(this.TL + this.H, edge) + pal.paint(label, pal.bold) +
        pal.paint(repeat(this.H, Math.max(0, fill - 1)) + this.TR, edge);
    }
    const bottom = pal.paint(this.BL + repeat(this.H, inner) + this.BR, edge);
    const result = [top];
    for (let ln of lines) {
      if (visibleLen(ln) === ln.length && ln.length > inner - 1) {
        ln = elide(ln, inner - 1);
      }
      const pad = inner - visibleLen(ln) - 1;
      const v = pal.paint(this.V, edge);
      result.push(v + " " + ln + repeat(" ", Math.max(0, pad)) + v);
    }
    result.push(bottom);
    return result;
  },
};

// A re-drawable region: successive render() calls overwrite in place.
class LiveBlock {
  constructor() {
    this.height = 0;
  }

  render(lines) {
    const buf = [];
    if (this.height) {
      buf.push(up(this.height));
      buf.push("\r");
      buf.push(CLEAR_DOWN);
    }
    buf.push(lines.join("\n"));
    buf.push("\n");
    out(buf.join(""));
    this.height = lines.length;
  }
}

// A pinned bottom spinner line with rows scrolling above it.
class Activity {
  constructor(pal) {
    this.pal = pal;
    this.frame = 0;
    this.label = "";
    this._active = false;
  }

  _spinline() {
    const glyph = this.pal.paint(SPIN_FRAMES[this.frame % SPIN_FRAMES.length],
      this.pal.gradFg(0.5));
    return "  " + glyph + " " + this.pal.dimmed(this.label);
  }

  start(label) {
    this.label = label;
    this._active = true;
    out(this._spinline());
  }

  setLabel(label) {
    this.label = label;
  }

  tick() {
    if (!this._active) return;
    this.frame += 1;
    out("\r" + CLEAR_LINE + this._spinline());
  }

  emit(row) {
    out("\r" + CLEAR_LINE + row + "\n");
    if (this._active) out(this._spinline());
  }

  stop() {
    if (this._active) out("\r" + CLEAR_LINE);
    this._active = false;
  }
}

// --------------------------------------------------------------------------
// Preflight probes
// --------------------------------------------------------------------------

const PASS = "PASS";
const WARN = "WARN";
const FAIL = "FAIL";
const GLYPH = { PASS: "✔", WARN: "△", FAIL: "✘" };

function toolVersion(binary, args) {
  let res;
  try {
    res = spawnSync(binary, args, { encoding: "utf8", timeout: 5000 });
  } catch (e) {
    return null;
  }
  if (!res || res.error) return null;
  const text = ((res.stdout || "") + (res.stderr || "")).trim();
  const first = text.split("\n")[0] || "";
  const m = first.match(/\d+\.\d+(\.\d+)?/);
  return m ? m[0] : (first || "found");
}

function probePython() {
  let res;
  try {
    res = spawnSync("python3", ["--version"], { encoding: "utf8", timeout: 5000 });
  } catch (e) {
    return [FAIL, "not found"];
  }
  if (!res || res.error) return [FAIL, "not found"];
  const text = ((res.stdout || "") + (res.stderr || "")).trim();
  const m = text.match(/(\d+)\.(\d+)(?:\.(\d+))?/);
  if (!m) return [FAIL, "unknown"];
  const major = parseInt(m[1], 10);
  const minor = parseInt(m[2], 10);
  const ver = m[3] !== undefined ? m[1] + "." + m[2] + "." + m[3] : m[1] + "." + m[2];
  const okVer = major > 3 || (major === 3 && minor >= 8);
  return [okVer ? PASS : FAIL, ver];
}

function probeGit() {
  const v = toolVersion("git", ["--version"]);
  return v === null ? [FAIL, "not found"] : [PASS, v];
}

function probeBash() {
  const v = toolVersion("bash", ["--version"]);
  return v === null ? [FAIL, "not found"] : [PASS, v];
}

function probeClaude() {
  const v = toolVersion("claude", ["--version"]);
  return v === null
    ? [WARN, "not found - install Claude Code to use the company"]
    : [PASS, v];
}

function probeNode() {
  // Self-evidently present: we are running inside Node.
  return [PASS, process.version.replace(/^v/, "")];
}

function probeNpx() {
  const v = toolVersion("npx", ["--version"]);
  return v === null
    ? [WARN, "not found - needed for browser QA screenshots"]
    : [PASS, v];
}

const PROBES = [
  { name: "python3 >= 3.8", hard: true, reason: "required by the enforcement hooks", fn: probePython },
  { name: "git", hard: true, reason: "required by the enforcement hooks", fn: probeGit },
  { name: "bash", hard: true, reason: "required by the enforcement hooks", fn: probeBash },
  { name: "claude CLI", hard: false, fn: probeClaude },
  { name: "node", hard: false, fn: probeNode },
  { name: "npx", hard: false, fn: probeNpx },
];

// --------------------------------------------------------------------------
// Source inventory (for the confirm summary)
// --------------------------------------------------------------------------

function sourceCounts() {
  function countFiles(rel, pattern) {
    const d = path.join(ROOT, rel);
    let entries;
    try {
      entries = fs.readdirSync(d);
    } catch (e) {
      return 0;
    }
    return entries.filter((f) => pattern.test(f)).length;
  }
  function countDirs(rel) {
    const d = path.join(ROOT, rel);
    let entries;
    try {
      entries = fs.readdirSync(d);
    } catch (e) {
      return 0;
    }
    return entries.filter((f) => {
      try {
        return fs.statSync(path.join(d, f)).isDirectory();
      } catch (e) {
        return false;
      }
    }).length;
  }
  return {
    agents: countFiles(".claude/agents", /\.md$/),
    skills: countDirs(".claude/skills"),
    hooks: countFiles(".claude/hooks", /\.py$/),
  };
}

// --------------------------------------------------------------------------
// Target validation
// --------------------------------------------------------------------------

function expandUser(p) {
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

function realpathOr(p) {
  try {
    return fs.realpathSync(p);
  } catch (e) {
    return p;
  }
}

function validateTarget(raw) {
  if (!raw || !raw.trim()) return [false, "", "enter a directory"];
  const p = path.resolve(expandUser(raw.trim()));
  let st;
  try {
    st = fs.statSync(p);
  } catch (e) {
    return [false, p, "does not exist - enter an existing directory"];
  }
  if (!st.isDirectory()) return [false, p, "not a directory"];
  if (realpathOr(p) === realpathOr(ROOT)) {
    return [false, p, "that is the claude-company repo itself - pick your project"];
  }
  try {
    fs.accessSync(p, fs.constants.W_OK);
  } catch (e) {
    return [false, p, "not writable - check permissions"];
  }
  const isGit = fs.existsSync(path.join(p, ".git"));
  let n = 0;
  try {
    n = fs.readdirSync(p).length;
  } catch (e) {
    n = 0;
  }
  if (isGit) return [true, p, "git repo, " + n + " entries"];
  return [true, p, "directory exists, not a git repo - will still install"];
}

// --------------------------------------------------------------------------
// TUI screens
// --------------------------------------------------------------------------

const TAGLINE = "An AI software company you drop into your repo.";

// Paint a plain wordmark char-by-char along the purple gradient, bold. Used as
// the narrow-terminal fallback so the hero never renders clipped/wrapped art.
function heroWordmark(pal, text) {
  if (!pal.enabled) return text;
  const parts = [];
  for (let i = 0; i < text.length; i++) {
    const t = text.length > 1 ? i / (text.length - 1) : 0;
    parts.push(pal.bold + pal.gradFg(t) + text[i]);
  }
  return parts.join("") + pal.reset;
}

function drawHero(pal) {
  const width = termWidth();
  out(CLEAR_SCREEN);

  const claude = heroRows("CLAUDE");
  const company = heroRows("COMPANY");
  const artWidth = Math.max(
    Math.max.apply(null, claude.map(visibleLen)),
    Math.max.apply(null, company.map(visibleLen)),
  );

  const lines = [];
  if (width >= artWidth + 4) {
    // Full block-art hero: CLAUDE stacked over COMPANY with one line-gap, each
    // of the 12 art rows painted top-to-bottom along the purple gradient
    // (#6D5BD0 at the top row through #B478F0 at the bottom).
    const total = claude.length + company.length;
    for (let i = 0; i < claude.length; i++) {
      const t = i / (total - 1);
      lines.push(center(pal.paint(claude[i], pal.gradFg(t), pal.bold), width));
    }
    lines.push("");
    for (let i = 0; i < company.length; i++) {
      const t = (claude.length + i) / (total - 1);
      lines.push(center(pal.paint(company[i], pal.gradFg(t), pal.bold), width));
    }
    lines.unshift("", "");
  } else {
    // Too narrow for the art: typographic wordmark instead of clipped letters.
    lines.push("", "");
    lines.push(center(heroWordmark(pal, "claude-company"), width));
  }
  lines.push("");
  lines.push(center(pal.dimmed(TAGLINE), width));
  lines.push("");
  lines.push(rule(pal, width, true));
  lines.push("");
  lines.push(center(pal.dimmed("press any key to begin  -  q or Esc to quit"), width));
  out(lines.join("\n") + "\n");
}

async function screenHero(term, pal) {
  drawHero(pal);
  for (;;) {
    const key = await term.readKey(0.5);
    if (key === null) {
      drawHero(pal);
      continue;
    }
    if (key === "q" || key === "Q" || key === KEY_ESC) return false;
    return true;
  }
}

function preflightRow(pal, name, status, detail, width, spinFrame) {
  let glyph;
  let right;
  if (status === null) {
    glyph = pal.paint(SPIN_FRAMES[spinFrame % SPIN_FRAMES.length], pal.gradFg(0.5));
    right = pal.dimmed("checking...");
  } else {
    const color = { PASS: GREEN, WARN: YELLOW, FAIL: RED }[status];
    glyph = pal.paint(GLYPH[status], pal.fg(color));
    right = pal.paint(detail, status !== PASS ? pal.fg(color) : pal.dim);
  }
  const left = "  " + glyph + " " + name;
  const gap = width - visibleLen(left) - visibleLen(right) - 2;
  return left + repeat(" ", Math.max(1, gap)) + right;
}

async function screenPreflight(term, pal) {
  const width = termWidth();
  out(CLEAR_SCREEN);
  const header = [
    "",
    " " + sectionHeader(pal, "Preflight"),
    " " + pal.dimmed("checking your machine has what the company needs"),
    "",
  ];
  out(header.join("\n") + "\n");

  const block = new LiveBlock();
  const results = [];
  const statuses = PROBES.map(() => null);

  function render(spin) {
    const rows = [];
    for (let i = 0; i < PROBES.length; i++) {
      const st = statuses[i];
      if (st === null) {
        rows.push(preflightRow(pal, PROBES[i].name, null, "", width, spin));
      } else {
        rows.push(preflightRow(pal, PROBES[i].name, st[0], st[1], width, spin));
      }
    }
    block.render(rows);
  }

  render(0);
  for (let i = 0; i < PROBES.length; i++) {
    const start = Date.now();
    const result = PROBES[i].fn();
    let frame = 0;
    while (Date.now() - start < 360) {
      render(frame);
      // eslint-disable-next-line no-await-in-loop
      await sleep(SPIN_INTERVAL * 1000);
      frame += 1;
    }
    statuses[i] = result;
    results.push([PROBES[i], result[0], result[1]]);
    render(frame);
  }

  const hardFail = results.filter((r) => r[0].hard && r[1] === FAIL);
  return [hardFail.length === 0, results];
}

function screenPreflightFail(pal, results) {
  const width = termWidth();
  const missing = results.filter((r) => r[0].hard && r[1] === FAIL).map((r) => r[0].name);
  const lines = [
    pal.paint("A required tool is missing.", pal.fg(RED), pal.bold),
    "",
    "claude-company needs these to run its enforcement hooks:",
  ];
  for (const name of missing) {
    lines.push("  " + pal.paint("✘ " + name, pal.fg(RED)));
  }
  lines.push("");
  lines.push(pal.dimmed("Install the missing tool(s), then run ./install again."));
  const box = Frame.render(pal, lines, width, 0.0, "Cannot continue");
  out("\n" + box.join("\n") + "\n");
}

function completePath(value) {
  const expanded = expandUser(value);
  const directory = path.dirname(expanded) || ".";
  const partial = path.basename(expanded);
  let entries;
  try {
    entries = fs.readdirSync(directory);
  } catch (e) {
    return value;
  }
  const matches = entries.filter((e) => e.startsWith(partial));
  if (matches.length === 0) return value;
  let completed;
  if (matches.length === 1) {
    completed = matches[0];
  } else {
    completed = commonPrefix(matches);
    if (completed === partial) return value;
  }
  let full = path.join(directory, completed);
  let isDir = false;
  try {
    isDir = fs.statSync(expandUser(full)).isDirectory();
  } catch (e) {
    isDir = false;
  }
  if (isDir && matches.length === 1) full += path.sep;
  if (value.startsWith("~")) {
    const home = os.homedir();
    if (full.startsWith(home)) full = "~" + full.slice(home.length);
  }
  return full;
}

function commonPrefix(strings) {
  if (strings.length === 0) return "";
  let prefix = strings[0];
  for (const s of strings) {
    while (!s.startsWith(prefix)) {
      prefix = prefix.slice(0, -1);
      if (prefix === "") return "";
    }
  }
  return prefix;
}

async function screenTarget(term, pal) {
  out(CLEAR_SCREEN);
  const header = [
    "",
    " " + sectionHeader(pal, "Target project"),
    " " + pal.dimmed("where should the company move in? (Tab completes, Esc quits)"),
    "",
  ];
  out(header.join("\n") + "\n");

  let value = process.cwd();
  const block = new LiveBlock();

  function render() {
    const [ok, , msg] = validateTarget(value);
    const caret = pal.paint("█", pal.gradFg(0.5));
    const prompt = "  " + pal.paint("❯", pal.gradFg(0.4)) + " " + value + caret;
    let status;
    if (ok) {
      const color = msg.indexOf("git repo") >= 0 ? GREEN : YELLOW;
      status = pal.paint("  " + msg, pal.fg(color));
    } else {
      status = pal.paint("  " + msg, pal.fg(RED));
    }
    block.render([prompt, "", status]);
  }

  render();
  for (;;) {
    const key = await term.readKey(0.5);
    if (key === null) {
      render();
      continue;
    }
    if (key === KEY_ESC) return null;
    if (key === KEY_ENTER) {
      const [ok, p] = validateTarget(value);
      if (ok) return p;
      render();
      continue;
    }
    if (key === KEY_BACKSPACE) {
      value = value.slice(0, -1);
      render();
      continue;
    }
    if (key === KEY_TAB) {
      value = completePath(value);
      render();
      continue;
    }
    if (!NAMED_KEYS.has(key) && key.length === 1 && isPrintable(key)) {
      value += key;
      render();
    }
  }
}

function isPrintable(ch) {
  const code = ch.charCodeAt(0);
  return code >= 0x20 && code !== 0x7f;
}

function makeOptions(detectGates, orientation) {
  return {
    items: [
      ["Auto-detect this project's gates (test/lint commands) after install", detectGates],
      ["Show the 60-second orientation at the end", orientation],
    ],
  };
}

async function screenOptions(term, pal, opts) {
  out(CLEAR_SCREEN);
  const header = [
    "",
    " " + sectionHeader(pal, "Options"),
    " " + pal.dimmed("arrows or j/k move  -  space toggles  -  Enter confirms"),
    "",
  ];
  out(header.join("\n") + "\n");

  let cursor = 0;
  const block = new LiveBlock();

  function render() {
    const rows = [];
    for (let i = 0; i < opts.items.length; i++) {
      const [label, on] = opts.items[i];
      const mark = on ? pal.paint("◉", pal.gradFg(0.5)) : pal.dimmed("◯");
      const pointer = i === cursor ? pal.paint("❯", pal.gradFg(0.4)) : " ";
      const text = i === cursor ? pal.paint(label, pal.bold) : label;
      rows.push("  " + pointer + " " + mark + "  " + text);
    }
    rows.push("");
    rows.push("  " + pal.dimmed("[ Enter to confirm ]"));
    block.render(rows);
  }

  render();
  for (;;) {
    const key = await term.readKey(0.5);
    if (key === null) {
      render();
      continue;
    }
    if (key === KEY_ESC) return null;
    if (key === KEY_UP || key === "k") {
      cursor = (cursor - 1 + opts.items.length) % opts.items.length;
      render();
    } else if (key === KEY_DOWN || key === "j") {
      cursor = (cursor + 1) % opts.items.length;
      render();
    } else if (key === " ") {
      opts.items[cursor][1] = !opts.items[cursor][1];
      render();
    } else if (key === KEY_ENTER) {
      return opts;
    }
  }
}

async function screenConfirm(term, pal, target, opts) {
  const width = termWidth();
  out(CLEAR_SCREEN);
  const counts = sourceCounts();
  const header = [
    "",
    " " + sectionHeader(pal, "Ready to install"),
    "",
  ];
  out(header.join("\n") + "\n");

  const kv = (k, v) => pal.dimmed(padRight(k, 10)) + "  " + v;
  const detect = opts.items[0][1];
  const orient = opts.items[1][1];
  const flag = (on) => (on ? pal.paint("on", pal.fg(GREEN)) : pal.dimmed("off"));

  const lines = [
    kv("target", pal.paint(elide(target, width - 16), pal.bold)),
    "",
    kv("installs", "agents " + counts.agents + ", skills " + counts.skills +
      ", hooks " + counts.hooks),
    kv("", "canon docs, templates, and company/state scaffolds"),
    "",
    kv("gates", flag(detect) + pal.dimmed("  (auto-detect after install)")),
    kv("tour", flag(orient) + pal.dimmed("  (60-second orientation)")),
    "",
    pal.dimmed("The installer merges with your settings and never overwrites your state."),
  ];
  const box = Frame.render(pal, lines, width, 0.5);
  out(box.join("\n") + "\n\n");
  const prompt = "  " +
    (pal.paint("Enter", pal.gradFg(0.5), pal.bold) + pal.dimmed(" install")) +
    "   " +
    (pal.paint("Esc", pal.bold) + pal.dimmed(" cancel"));
  out(prompt + "\n");

  for (;;) {
    const key = await term.readKey(0.5);
    if (key === null) continue;
    if (key === KEY_ENTER) return true;
    if (key === KEY_ESC || key === "q" || key === "Q") return false;
  }
}

// --------------------------------------------------------------------------
// Install streaming
// --------------------------------------------------------------------------

const RE_INFO = /^==> (.*)$/;
const RE_OK = /^  ok (.*)$/;
const RE_KEEP = /^  keep (.*)$/;
const RE_WARN = /^warning: (.*)$/;
const RE_ERR = /^error: (.*)$/;

const EPILOGUE_PREFIXES = [
  "source:", "target:", "1.", "2.", "3.", "4.", "cd ", "claude",
  "/company-init", "/onboard", "/orchestrator", "Next steps:", "Configure",
  "In Claude Code", "bash company",
];

function styleInstallLine(pal, line) {
  let m = line.match(RE_INFO);
  if (m) {
    const title = m[1];
    if (title === "claude-company installer" || title === "claude-company installed") {
      return ["meta", null];
    }
    return ["section", "  " + sectionHeader(pal, title)];
  }
  m = line.match(RE_OK);
  if (m) {
    const glyph = pal.paint("✔", pal.fg(GREEN));
    return ["ok", "    " + glyph + " " + pal.dimmed(m[1])];
  }
  m = line.match(RE_KEEP);
  if (m) {
    const glyph = pal.paint("∙", pal.dim);
    return ["keep", "    " + glyph + " " + pal.dimmed(m[1] + " (kept)")];
  }
  m = line.match(RE_WARN);
  if (m) {
    const glyph = pal.paint("△", pal.fg(YELLOW));
    return ["warn", "    " + glyph + " " + pal.paint(m[1], pal.fg(YELLOW))];
  }
  m = line.match(RE_ERR);
  if (m) {
    return ["error", "    " + pal.paint("✘ " + m[1], pal.fg(RED))];
  }
  if (!line.trim()) return null;
  const stripped = line.trim();
  for (const pfx of EPILOGUE_PREFIXES) {
    if (stripped.startsWith(pfx)) return null;
  }
  return ["dim", "    " + pal.dimmed(line.replace(/\s+$/, ""))];
}

function runInstallStream(pal, target, activity) {
  return new Promise((resolve) => {
    const env = Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" });
    const proc = spawn("bash", [INSTALL_SH, target], { env, stdio: ["ignore", "pipe", "pipe"] });
    const tail = [];

    function handle(raw) {
      tail.push(raw);
      if (tail.length > 40) tail.splice(0, tail.length - 40);
      const styled = styleInstallLine(pal, raw);
      if (styled === null) return;
      const kind = styled[0];
      const text = styled[1];
      if (kind === "section" && activity) {
        const m = raw.match(RE_INFO);
        if (m) activity.setLabel(m[1]);
      }
      if (text === null) return;
      if (activity) activity.emit(text);
      else out(text + "\n");
    }

    let bufOut = "";
    let bufErr = "";
    proc.stdout.on("data", (d) => {
      bufOut += d.toString("utf8");
      let idx;
      while ((idx = bufOut.indexOf("\n")) >= 0) {
        handle(bufOut.slice(0, idx));
        bufOut = bufOut.slice(idx + 1);
      }
    });
    proc.stderr.on("data", (d) => {
      bufErr += d.toString("utf8");
      let idx;
      while ((idx = bufErr.indexOf("\n")) >= 0) {
        handle(bufErr.slice(0, idx));
        bufErr = bufErr.slice(idx + 1);
      }
    });

    let timer = null;
    if (activity) timer = setInterval(() => activity.tick(), SPIN_INTERVAL * 1000);

    proc.on("error", () => {
      if (timer) clearInterval(timer);
      resolve([1, tail]);
    });
    proc.on("close", (code) => {
      if (timer) clearInterval(timer);
      if (bufOut.trim()) handle(bufOut);
      if (bufErr.trim()) handle(bufErr);
      resolve([code === null ? 1 : code, tail]);
    });
  });
}

async function screenInstall(pal, target) {
  out(CLEAR_SCREEN);
  const header = [
    "",
    " " + sectionHeader(pal, "Installing"),
    "",
  ];
  out(header.join("\n") + "\n");
  const activity = new Activity(pal);
  activity.start("starting install");
  const [rc, tail] = await runInstallStream(pal, target, activity);
  activity.stop();
  return [rc, tail];
}

function screenInstallError(pal, tail) {
  const width = termWidth();
  const body = [pal.paint("The install did not finish cleanly.", pal.fg(RED), pal.bold), ""];
  for (const line of tail.slice(-14)) {
    body.push(pal.dimmed(line.replace(/\s+$/, "").slice(0, width - 4)));
  }
  const box = Frame.render(pal, body, width, 0.0, "install.sh failed");
  out("\n" + box.join("\n") + "\n");
}

// --------------------------------------------------------------------------
// Gates detection
// --------------------------------------------------------------------------

function runGatesDetect(target, write) {
  const script = path.join(target, ".claude", "hooks", "gates_detect.py");
  if (!fs.existsSync(script)) return null;
  const env = Object.assign({}, process.env, {
    CLAUDE_PROJECT_DIR: target,
    PYTHONDONTWRITEBYTECODE: "1",
  });
  const args = [script];
  if (write) args.push("--write");
  let res;
  try {
    res = spawnSync("python3", args, { cwd: target, env, encoding: "utf8", timeout: 60000 });
  } catch (e) {
    return null;
  }
  if (!res || res.error) return null;
  const text = res.stdout || "";
  for (const line of text.split("\n")) {
    if (line.startsWith("GATES_JSON: ")) {
      try {
        return JSON.parse(line.slice("GATES_JSON: ".length));
      } catch (e) {
        return null;
      }
    }
  }
  return null;
}

function screenGates(pal, data) {
  const width = termWidth();
  out("\n " + sectionHeader(pal, "Gate detection") + "\n\n");
  if (!data || data.status === "no_stack") {
    out("  " + pal.dimmed(
      "no stack detected - company/gates.config keeps its placeholders for the agents to fill.") + "\n");
    return;
  }
  const stacks = (data.stacks && data.stacks.join(", ")) || "unknown";
  const lines = [pal.dimmed("stack: " + stacks), ""];
  const proposed = data.proposed || [];
  if (proposed.length) {
    for (const g of proposed) {
      const name = pal.paint(padRight(g.name || "", 10), pal.fg(GREEN));
      lines.push(name + " " + pal.dimmed(g.command || ""));
    }
  } else {
    lines.push(pal.dimmed("no invocable gate commands on this machine."));
  }
  const status = data.status;
  if (status === "wrote") {
    lines.push("");
    lines.push(pal.paint("wrote " + proposed.length + " gate(s) to company/gates.config", pal.fg(GREEN)));
  } else if (status === "preserved_existing") {
    lines.push("");
    lines.push(pal.dimmed("existing real gates preserved - not overwritten."));
  }
  const box = Frame.render(pal, lines, width, 0.5);
  out(box.join("\n") + "\n");
}

// --------------------------------------------------------------------------
// Done screen
// --------------------------------------------------------------------------

function screenDone(pal, target, orientation) {
  const width = termWidth();
  out("\n" + rule(pal, width, true) + "\n\n");
  const check = pal.paint("✔", pal.fg(GREEN), pal.bold);
  out(center(check + "  " + pal.brand("claude-company is installed"), width) + "\n\n");

  const orch = pal.paint("/orchestrator build me <what you want>", pal.gradFg(0.5), pal.bold);
  if (orientation) {
    const targetLine = elide("Launch Claude Code in " + target, width - 12);
    const steps = [
      ["Open the company", targetLine],
      ["Give the order", "Type  " + orch],
      ["Review the evidence", "The company self-onboards, builds, and reports back with proof"],
    ];
    const blocks = [];
    for (let idx = 0; idx < steps.length; idx++) {
      const i = idx + 1;
      const [title, bodyText] = steps[idx];
      const num = pal.paint(" " + i + " ", pal.gradFg(i / 3.0), pal.bold);
      const inner = [
        num + " " + pal.paint(title, pal.bold),
        "   " + pal.dimmed(bodyText),
      ];
      const box = Frame.render(pal, inner, width - 4, i / 3.0);
      for (const ln of box) blocks.push("  " + ln);
      blocks.push("");
    }
    out(blocks.join("\n") + "\n");
    out("  " + pal.dimmed("More: docs/getting-started.md") + "\n\n");
  } else {
    out("  Next: open Claude Code in your project and run\n");
    out("    " + orch + "\n\n");
  }

  out("  " + pal.dimmed(
    "Re-run anytime - the installer never overwrites your settings or state.") + "\n");
}

// --------------------------------------------------------------------------
// TUI driver
// --------------------------------------------------------------------------

async function runTui(args, pal) {
  const term = new Terminal(pal).enter();
  try {
    if (!(await screenHero(term, pal))) {
      out("\n" + pal.dimmed("  Nothing installed.") + "\n");
      return EXIT_OK;
    }
    const [ok, results] = await screenPreflight(term, pal);
    if (!ok) {
      screenPreflightFail(pal, results);
      return EXIT_PREFLIGHT;
    }

    let target = null;
    if (args.target || args.positional) {
      const cand = args.target || args.positional;
      const [good, p] = validateTarget(cand);
      if (good) target = p;
    }
    if (target === null) {
      target = await screenTarget(term, pal);
      if (target === null) {
        out("\n" + pal.dimmed("  Install cancelled.") + "\n");
        return EXIT_CANCEL;
      }
    }

    const opts = makeOptions(args.detectGates, args.orientation);
    const chosen = await screenOptions(term, pal, opts);
    if (chosen === null) {
      out("\n" + pal.dimmed("  Install cancelled.") + "\n");
      return EXIT_CANCEL;
    }

    if (!(await screenConfirm(term, pal, target, chosen))) {
      out("\n" + pal.dimmed("  Install cancelled.") + "\n");
      return EXIT_CANCEL;
    }

    const [rc, tail] = await screenInstall(pal, target);
    if (rc !== 0) {
      screenInstallError(pal, tail);
      return EXIT_INSTALL;
    }

    if (chosen.items[0][1]) {
      const data = runGatesDetect(target, true);
      screenGates(pal, data);
    }

    screenDone(pal, target, chosen.items[1][1]);
    return EXIT_OK;
  } finally {
    term.restore();
  }
}

// --------------------------------------------------------------------------
// Plain (non-interactive) driver
// --------------------------------------------------------------------------

function runPlain(args) {
  const targetArg = args.target || args.positional;
  if (!targetArg) {
    process.stderr.write(
      "install: a target is required in non-interactive mode.\n" +
      "Usage: install --target /path/to/your/project [--yes]\n");
    return EXIT_USAGE;
  }

  // -- preflight --
  process.stdout.write("claude-company installer - preflight\n");
  const results = PROBES.map((p) => {
    const [status, detail] = p.fn();
    return [p, status, detail];
  });
  for (const [probe, status, detail] of results) {
    process.stdout.write("  [" + status + "] " + padRight(probe.name, 18) + " " + detail + "\n");
  }
  const hardFail = results.filter((r) => r[0].hard && r[1] === FAIL);
  if (hardFail.length) {
    const names = hardFail.map((r) => r[0].name).join(", ");
    process.stderr.write("install: missing required tool(s): " + names + "\n");
    process.stderr.write("install: these are required by the enforcement hooks.\n");
    return EXIT_PREFLIGHT;
  }

  // -- validate target --
  const [ok, p, msg] = validateTarget(targetArg);
  if (!ok) {
    process.stderr.write("install: target " + targetArg + ": " + msg + "\n");
    return EXIT_PREFLIGHT;
  }
  process.stdout.write("\ntarget: " + p + " (" + msg + ")\n");

  // -- run install.sh, streaming raw --
  process.stdout.write("\ninstalling...\n");
  const env = Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" });
  const res = spawnSync("bash", [INSTALL_SH, p], { env, stdio: "inherit" });
  const rc = res.status;
  if (res.error || rc !== 0) {
    process.stderr.write("install: install.sh failed (exit " + (rc === null ? 1 : rc) + ").\n");
    return EXIT_INSTALL;
  }

  // -- optional gate detection --
  if (args.detectGates) {
    process.stdout.write("\ndetecting gates...\n");
    const data = runGatesDetect(p, true);
    if (!data || data.status === "no_stack") {
      process.stdout.write("  no stack detected - gates.config keeps its placeholders.\n");
    } else {
      process.stdout.write("  stack: " + ((data.stacks && data.stacks.join(", ")) || "") + "\n");
      for (const g of data.proposed || []) {
        process.stdout.write("    " + padRight(g.name || "", 10) + " " + (g.command || "") + "\n");
      }
      if (data.status === "wrote") {
        process.stdout.write("  wrote " + (data.proposed || []).length + " gate(s) to company/gates.config\n");
      } else if (data.status === "preserved_existing") {
        process.stdout.write("  existing real gates preserved.\n");
      }
    }
  }

  // -- summary --
  const counts = sourceCounts();
  process.stdout.write("\nclaude-company installed into " + p + "\n");
  process.stdout.write("  agents " + counts.agents + ", skills " + counts.skills +
    ", hooks " + counts.hooks + ", canon docs, state scaffolds\n");
  process.stdout.write("  next: open Claude Code and run  /orchestrator build me <what you want>\n");
  return EXIT_OK;
}

// --------------------------------------------------------------------------
// Argument parsing and entry
// --------------------------------------------------------------------------

function helpText() {
  return [
    "Install claude-company - an AI software company you drop into your repo.",
    "",
    "Usage:",
    "  install [TARGET] [options]",
    "",
    "Options:",
    "  --target DIR         Target project directory (must already exist).",
    "  -y, --yes            Non-interactive; accept defaults (implies plain).",
    "  --plain              Force plain, non-interactive output.",
    "  --no-color           Monochrome output (NO_COLOR is honored too).",
    "  --detect-gates       Auto-detect gates after install (default).",
    "  --no-detect-gates    Skip gate auto-detection.",
    "  --orientation        Show the 60-second orientation (default).",
    "  --no-orientation     Skip the orientation on the done screen.",
    "  -h, --help           Show this help.",
    "",
    "Examples:",
    "  install                       full TUI",
    "  install --target ~/proj --yes non-interactive install",
    "  install ~/proj --plain        plain line-per-step output",
    "",
    "Exit codes: 0 ok, 1 usage, 2 preflight/target hard-fail, 3 install failure,",
    "130 cancelled.",
  ].join("\n");
}

function parseArgs(argv) {
  const args = {
    positional: null,
    target: null,
    yes: false,
    plain: false,
    noColor: false,
    detectGates: true,
    orientation: true,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      args.help = true;
    } else if (a === "-y" || a === "--yes") {
      args.yes = true;
    } else if (a === "--plain") {
      args.plain = true;
    } else if (a === "--no-color") {
      args.noColor = true;
    } else if (a === "--detect-gates") {
      args.detectGates = true;
    } else if (a === "--no-detect-gates") {
      args.detectGates = false;
    } else if (a === "--orientation") {
      args.orientation = true;
    } else if (a === "--no-orientation") {
      args.orientation = false;
    } else if (a === "--target") {
      args.target = argv[++i];
      if (args.target === undefined) {
        return { error: "install: --target requires a directory argument" };
      }
    } else if (a.startsWith("--target=")) {
      args.target = a.slice("--target=".length);
    } else if (a === "--") {
      // remaining are positional
      if (i + 1 < argv.length && args.positional === null) args.positional = argv[i + 1];
      break;
    } else if (a.startsWith("-") && a !== "-") {
      return { error: "install: unrecognized option '" + a + "'" };
    } else if (args.positional === null) {
      args.positional = a;
    } else {
      return { error: "install: unexpected extra argument '" + a + "'" };
    }
  }
  return { args };
}

function stdioIsTty() {
  return Boolean(process.stdin.isTTY) && Boolean(process.stdout.isTTY);
}

// Public entry: runs the installer. `argv` is the args after the `install`
// subcommand. Returns a Promise resolving to the process exit code.
async function run(argv) {
  const parsed = parseArgs(argv || []);
  if (parsed.error) {
    process.stderr.write(parsed.error + "\n\n");
    process.stderr.write(helpText() + "\n");
    return EXIT_PREFLIGHT;
  }
  const args = parsed.args;
  if (args.help) {
    process.stdout.write(helpText() + "\n");
    return EXIT_OK;
  }
  const pal = decidePalette(args.noColor);

  const interactive = stdioIsTty() && !args.yes && !args.plain &&
    Boolean(process.stdin.setRawMode);

  if (interactive) {
    return runTui(args, pal);
  }
  return runPlain(args);
}

module.exports = { run, helpText };
// Test-only surface: lets tests validate the hero font table and rendering
// without driving the interactive TUI. Not part of the public API.
module.exports._hero = { FONT_ANSI_SHADOW, HERO_ROWS, heroRows };
// Shared surface for the sibling `update` CLI (lib/update.js): the preflight
// probe table, target validation, path expansion, small formatting helper, and
// the canonical exit codes. Reused verbatim so update never forks install's
// preflight/target logic. Not a public package API.
module.exports._shared = {
  PROBES,
  validateTarget,
  expandUser,
  padRight,
  PASS, WARN, FAIL,
  EXIT_OK, EXIT_USAGE, EXIT_PREFLIGHT, EXIT_INSTALL, EXIT_CANCEL,
};

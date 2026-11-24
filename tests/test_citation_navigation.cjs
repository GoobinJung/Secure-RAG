const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class ElementStub {
  constructor() { this.listeners = {}; this.dataset = {}; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}

function setup() {
  const elements = new Map();
  const document = {
    body: {dataset: {sessionContext: "test-session"}},
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new ElementStub());
      return elements.get(id);
    },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/question.js"), "utf8"), {
    document, window: {addEventListener() {}}, Element: ElementStub,
  });
  return elements.get("chat-messages").listeners.click;
}

test("a citation opens and focuses its own exchange's source, leaving other turns untouched", () => {
  const click = setup();
  const source = {open: false, setAttribute() {}, focus(options) { this.focused = options.preventScroll; },
    scrollIntoView(options) { this.scrolled = options.block; }};
  const otherTurnSource = {open: false};
  const panel = {open: false};
  let removedOldHighlight = false;
  const exchange = {
    querySelector(selector) {
      if (selector === '.source-card[data-source-number="1"]') return source;
      if (selector === '[data-source-panel]') return panel;
      throw new Error("Unexpected target: " + selector);
    },
    querySelectorAll() { return [{removeAttribute() { removedOldHighlight = true; }}]; },
  };
  const reference = {dataset: {sourceNumber: "1"}, closest() { return exchange; }};
  const target = new ElementStub();
  target.closest = () => reference;
  click({target});
  assert.equal(panel.open, true);
  assert.equal(source.open, true);
  assert.equal(source.focused, true);
  assert.equal(source.scrolled, "nearest");
  assert.equal(otherTurnSource.open, false);
  assert.equal(removedOldHighlight, true);
});

test("invalid reference numbers do not query or open any source", () => {
  const click = setup();
  for (const number of ["0", "-1", "1.5", '1"] img', "NaN"]) {
    const target = new ElementStub();
    target.closest = () => ({dataset: {sourceNumber: number}, closest() {
      throw new Error("Invalid number reached source lookup");
    }});
    click({target});
  }
});

test("ordinary clicks and references without a supplied source are harmless", () => {
  const click = setup();
  const target = new ElementStub();
  target.closest = () => null;
  click({target});
  target.closest = () => ({dataset: {sourceNumber: "2"}, closest() {
    return {querySelector() { return null; }};
  }});
  click({target});
});

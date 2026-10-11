#!/usr/bin/env python3
"""
Website: jis WiFi se ye computer abhi juda hai, uske saare connected devices.

    python wifi_scanner.py --web
    docker compose up -d --build

Doosre area mein jao, us WiFi se is computer ko jodo, page dubara us network ki list dikhata hai.
Browser akela aas-paas ke phone nahi dekh sakta — scan isi computer se hota hai.
Docker tabhi WiFi dekhta hai jab container host network pe ho (Linux).
"""
import ipaddress
import json
import os
import re
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import wifi_scanner

MAC_OK = re.compile(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")
UNLOCK_CODE = "9199"

PAGE = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Is WiFi ke devices</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #121611; color: #e7f0df; font: 16px/1.4 ui-sans-serif, system-ui, sans-serif; }
  header, .wrap { padding: 18px; }
  h1 { margin: 0; font-size: 28px; line-height: 1.15; }
  .sub { color: #9aa892; margin: 6px 0 0; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button {
    background: #243022; color: #e7f0df; border: 1px solid #3d4d38;
    border-radius: 8px; padding: 8px 12px; cursor: pointer; font: inherit;
  }
  button.primary { background: #31461c; border-color: #6d8f32; color: #d6ff6a; }
  .meta { display: flex; gap: 16px; flex-wrap: wrap; color: #9aa892; padding: 0 18px; }
  .meta b { color: #e7f0df; }
  #alert {
    display: none; margin: 14px 18px 0; padding: 12px 14px; border-radius: 12px;
    background: #24310f; border: 1px solid #6d8f32; color: #d6ff6a;
  }
  #alert.show { display: block; }
  #err { color: #ff8b8b; padding: 8px 18px 0; }
  .panel { margin: 14px 18px 18px; background: #1b2119; border: 1px solid #2c3528; border-radius: 12px; overflow: auto; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 10px; white-space: nowrap; vertical-align: middle; }
  th { color: #9aa892; font-size: 12px; border-bottom: 1px solid #2c3528; }
  td { border-bottom: 1px solid #232a21; }
  tr.c0 td { color: #5ce1ff; }
  tr.c1 td { color: #5ddea0; }
  tr.c2 td { color: #f0d060; }
  tr.c3 td { color: #e48bff; }
  tr.c4 td { color: #8eb0ff; }
  tr.c5 td { color: #ff8b8b; }
  tr.c6 td { color: #f4f4f4; }
  .new { color: #ff8b8b; font-weight: 700; }
  .namebox { display: flex; gap: 4px; }
  .namebox input {
    width: 120px; background: #121611; color: #e7f0df;
    border: 1px solid #3d4d38; border-radius: 6px; padding: 4px 6px;
  }
  .empty { color: #9aa892; padding: 16px; }
  .log h2 { margin: 0; padding: 12px 12px 0; font-size: 14px; color: #9aa892; }
  .log .rows { padding: 8px 12px 12px; }
  .log .rows div { padding: 6px 0; border-bottom: 1px solid #232a21; }
  .log .when { color: #9aa892; margin-right: 10px; }
  .log .connect { color: #5ddea0; font-weight: 700; margin-right: 10px; }
  .log .disconnect { color: #ff8b8b; font-weight: 700; margin-right: 10px; }
  button.mac {
    background: none; border: 0; padding: 0; color: inherit;
    font: inherit; cursor: pointer; text-decoration: underline;
  }
  #hist {
    display: none; position: fixed; inset: 0; z-index: 40;
    background: rgba(0, 0, 0, 0.55); padding: 64px 16px 16px;
  }
  #hist.show { display: block; }
  #hist .rows { margin-top: 8px; max-height: 60vh; overflow: auto; }
  #hist .rows div { padding: 6px 0; border-bottom: 1px solid #232a21; }
  button.dot {
    position: fixed; top: 12px; right: 12px; z-index: 20;
    width: 14px; height: 14px; padding: 0; border: 0; border-radius: 50%;
    background: #8eb0ff;
  }
  #gate {
    display: none; position: fixed; inset: 0; z-index: 30;
    background: rgba(0, 0, 0, 0.55); padding: 64px 16px 16px;
  }
  #gate.show { display: block; }
  .sheet {
    width: min(440px, 100%); margin: 0 0 0 auto; background: #1b2119;
    border: 1px solid #3d4d38; border-radius: 14px; padding: 16px;
  }
  .sheet.wide {
    width: min(1080px, 100%); max-height: calc(100vh - 88px); overflow: auto;
  }
  .sheet .panel { margin: 12px 0 0; }
  .sheet .sub { margin: 0; }
  .sheet h2 { margin: 0 0 12px; font-size: 18px; color: #e7f0df; }
  .sheet input {
    width: 100%; margin-bottom: 10px; background: #121611; color: #e7f0df;
    border: 1px solid #3d4d38; border-radius: 8px; padding: 8px 10px; font: inherit;
  }
  .sheet .rowb { display: flex; gap: 8px; justify-content: flex-end; }
  #gatemsg { min-height: 1.2em; color: #ff8b8b; margin: 8px 0 0; }
  .wifi { padding: 8px 0; border-bottom: 1px solid #232a21; }
  .wifi b { display: block; }
  .wifi span, .iface { color: #9aa892; font-size: 14px; }
  .iface { padding: 4px 0; }
  .on { color: #d6ff6a; }
  #tabs { display: none; gap: 8px; padding: 14px 18px 0; }
  #tabs.show { display: flex; }
  button.tab.on { background: #31461c; border-color: #6d8f32; color: #d6ff6a; }
</style>
</head>
<body>
<button id="dot" class="dot" type="button" aria-label="Network"></button>
<div id="gate">
  <div class="sheet">
    <h2 id="gateTitle">Code</h2>
    <form id="gateForm">
      <input id="gateCode" inputmode="numeric" autocomplete="off" aria-label="Code">
      <div class="rowb">
        <button type="button" id="gateClose">Band</button>
        <button type="submit" class="primary" id="gateGo">Kholo</button>
      </div>
    </form>
    <p id="gateMsg"></p>
    <div id="gateList"></div>
  </div>
</div>
<header>
  <h1 id="ssid">Connected devices</h1>
  <p class="sub" id="sub">Website pe is WiFi ki list yahan dikhegi.</p>
</header>
<div id="tabs">
  <button type="button" id="tabWifi" class="tab on">WiFi</button>
  <button type="button" id="tabInternal" class="tab">Internal</button>
</div>
<div class="meta">
  <div>Devices <b id="count">0</b></div>
  <div id="status">Scan ho raha hai...</div>
</div>
<div id="err"></div>
<div id="alert"></div>
<div class="panel">
  <table>
    <thead>
      <tr><th>IP</th><th>MAC</th><th>Vendor</th><th>Type</th><th>Hostname</th><th>Ports</th><th>Naam</th></tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <div class="empty" id="empty">Scan chal raha hai.</div>
</div>
<div class="panel log" id="logPanel">
  <h2>Connect / Disconnect</h2>
  <div class="rows" id="log"></div>
</div>
<div id="hist">
  <div class="sheet wide">
    <h2 id="histTitle">History</h2>
    <p class="sub" id="histSub"></p>
    <div class="rows" id="histRows"></div>
    <div class="rowb"><button type="button" id="histClose">Band</button></div>
  </div>
</div>
<script>
const ssidEl = document.getElementById("ssid");
const subEl = document.getElementById("sub");
const rowsEl = document.getElementById("rows");
const emptyEl = document.getElementById("empty");
const alertEl = document.getElementById("alert");
let tableKey = "";
let seenGen = -1;
let stateFrom = "";
let postedAt = 0;
let view = "public";
let unlockCode = "";
let internalData = null;
let publicData = null;
let logKey = "";
let historyEvents = [];

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function render(devices) {
  const key = JSON.stringify(devices);
  if (key === tableKey) return;
  tableKey = key;
  rowsEl.textContent = "";
  emptyEl.style.display = devices.length ? "none" : "block";
  devices.forEach((d) => {
    const tr = el("tr", null, "c" + (d.color || 0));
    ["ip", "mac", "vendor", "type", "hostname"].forEach((field) => {
      if (field === "mac" && d.mac && d.mac !== "?" && d.mac !== "-") {
        const td = el("td");
        td.appendChild(macButton(d.mac));
        tr.appendChild(td);
      } else {
        tr.appendChild(el("td", d[field] || ""));
      }
    });
    tr.appendChild(el("td", (d.ports || []).join(",")));
    const nameTd = el("td");
    if (!d.mac || d.mac === "?" || d.mac === "-" || d.name === "Ye computer") {
      nameTd.appendChild(el("span", d.name || "", d.name === "NEW" ? "new" : ""));
    } else {
      const box = el("div", null, "namebox");
      const input = document.createElement("input");
      input.value = d.name === "NEW" ? "" : (d.name || "");
      input.placeholder = d.name === "NEW" ? "NEW" : "naam";
      input.setAttribute("aria-label", "Device ka naam");
      const btn = el("button", "Save");
      btn.type = "button";
      btn.addEventListener("click", () => saveName(d.mac, input.value));
      box.appendChild(input);
      box.appendChild(btn);
      nameTd.appendChild(box);
    }
    tr.appendChild(nameTd);
    rowsEl.appendChild(tr);
  });
}

async function saveName(mac, name) {
  const url = view === "internal" ? "/api/name" : (stateFrom || "/api/name");
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mac: mac, name: name })
  });
  tableKey = "";
  if (view === "internal") refreshInternal();
  else tick();
}

function paintChrome(data, heading, sub, emptyWaiting) {
  const devices = data.devices || [];
  document.getElementById("count").textContent = String(devices.length);
  document.getElementById("err").textContent = data.error || data.warning || "";
  ssidEl.textContent = heading;
  subEl.textContent = sub;
  if (!devices.length) {
    emptyEl.textContent = data.scanning ? "Scan chal raha hai." : emptyWaiting;
  }
  if (data.scanning) document.getElementById("status").textContent = "Scan ho raha hai...";
  else if (!data.updated) document.getElementById("status").textContent = "Scan ka intezar";
  else {
    const ago = Math.max(0, Math.round(Date.now() / 1000 - data.updated));
    document.getElementById("status").textContent = "Aakhri scan " + ago + "s pehle";
  }
  render(devices);
  renderLog(data.events || []);
}

function macButton(mac) {
  const btn = el("button", mac, "mac");
  btn.type = "button";
  btn.addEventListener("click", () => showHistory(mac));
  return btn;
}

function clockText(at) {
  if (!at) return "";
  return new Date(at * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function logLine(ev, withMac) {
  const row = el("div");
  row.appendChild(el("span", clockText(ev.at), "when"));
  const left = ev.action === "disconnect";
  row.appendChild(el("span", left ? "Disconnect" : "Connect", left ? "disconnect" : "connect"));
  const bits = [ev.name && ev.name !== "NEW" ? ev.name : "", ev.ip, ev.hostname];
  if (withMac && ev.mac && ev.mac !== "?" && ev.mac !== "-") bits.push(ev.mac);
  row.appendChild(document.createTextNode(bits.filter(Boolean).join("   ")));
  return row;
}

function showHistory(mac) {
  const want = String(mac || "").toUpperCase();
  const rows = historyEvents.filter((ev) => String(ev.mac || "").toUpperCase() === want);
  document.getElementById("histTitle").textContent = mac;
  document.getElementById("histSub").textContent = rows.length ? (rows.length + " events") : "Is MAC ki history abhi nahi hai.";
  const box = document.getElementById("histRows");
  box.textContent = "";
  rows.forEach((ev) => box.appendChild(logLine(ev, false)));
  document.getElementById("hist").classList.add("show");
}

function renderLog(events) {
  historyEvents = events || [];
  const box = document.getElementById("log");
  const key = JSON.stringify(historyEvents);
  if (key === logKey) return;
  logKey = key;
  box.textContent = "";
  if (!historyEvents.length) {
    box.appendChild(el("div", "Abhi koi connect ya disconnect nahi hua."));
    return;
  }
  historyEvents.forEach((ev) => {
    const row = logLine(ev, false);
    if (ev.mac && ev.mac !== "?" && ev.mac !== "-") {
      row.appendChild(document.createTextNode("   "));
      row.appendChild(macButton(ev.mac));
    }
    box.appendChild(row);
  });
}

function paintPublic(data) {
  const title = data.ssid || data.net || "WiFi";
  document.getElementById("tabWifi").textContent = title;
  const sub = title === "WiFi" ? "Website pe is WiFi ki list yahan dikhegi." : "Is WiFi ke connected devices.";
  paintChrome(data, title, sub, "Is WiFi ki list abhi website pe nahi hai.");
}

function paintInternal() {
  const data = internalData || {};
  const devices = data.server_devices || [];
  paintChrome({
    devices: devices,
    events: data.events || [],
    scanning: !!data.scanning,
    updated: data.updated,
    error: "",
    warning: ""
  }, "Internal", data.ssid || "Deploy system ke connected devices.", "Is system ka scan abhi nahi aaya.");
}

function showView(next) {
  view = next;
  tableKey = "";
  logKey = "";
  document.getElementById("tabWifi").classList.toggle("on", view === "public");
  document.getElementById("tabInternal").classList.toggle("on", view === "internal");
  if (view === "internal") paintInternal();
  else if (publicData) paintPublic(publicData);
}

async function refreshInternal() {
  if (!unlockCode) return;
  try {
    const res = await fetch("/api/networks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: unlockCode })
    });
    if (!res.ok) return;
    internalData = await res.json();
    if (view === "internal") paintInternal();
  } catch (e) {}
}

async function localState() {
  if (location.hostname === "localhost" || location.hostname === "127.0.0.1") return null;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 800);
  try {
    const res = await fetch("http://127.0.0.1:8765/api/state", { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) return null;
    const data = await res.json();
    if (data && (data.connected || (data.devices || []).length)) return data;
  } catch (e) {
  } finally {
    clearTimeout(timer);
  }
  return null;
}

async function publish(data) {
  if (!data || !data.scanner_mac || !(data.devices || []).length) return;
  if (data.updated && data.updated === postedAt) return;
  postedAt = data.updated || 0;
  try {
    const res = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: "9199",
        scanner_mac: data.scanner_mac,
        ssid: data.ssid || data.net || "",
        my_ip: data.my_ip || "",
        net: data.net || "",
        devices: data.devices
      })
    });
    if (!res.ok) postedAt = 0;
  } catch (e) {
    postedAt = 0;
  }
}

async function tick() {
  let data;
  stateFrom = "";
  let remote = null;
  try {
    remote = await (await fetch("/api/state")).json();
  } catch (e) {
    document.getElementById("status").textContent = "Server se connection nahi";
    return;
  }
  const local = await localState();
  if (local && (local.devices || []).length) {
    data = local;
    stateFrom = "http://127.0.0.1:8765/api/name";
    publish(local);
  } else {
    data = remote;
  }
  publicData = data;
  if (view === "public") paintPublic(data);
  else document.getElementById("tabWifi").textContent = data.ssid || data.net || "WiFi";
  if (typeof data.generation === "number" && data.generation !== seenGen) {
    if (seenGen !== -1 && data.connected && view === "public") {
      alertEl.textContent = "List update ho gayi. Devices: " + (data.devices || []).length;
      alertEl.classList.add("show");
    }
    seenGen = data.generation;
  }
  if (unlockCode) refreshInternal();
}

const gate = document.getElementById("gate");
const gateForm = document.getElementById("gateForm");
const gateList = document.getElementById("gateList");
const gateMsg = document.getElementById("gateMsg");
const gateCode = document.getElementById("gateCode");
let dotClicks = 0;
let dotAt = 0;

function sheet() {
  return document.querySelector("#gate .sheet");
}

function openGate() {
  gate.classList.add("show");
  sheet().classList.remove("wide");
  gateList.textContent = "";
  gateMsg.textContent = "";
  gateForm.hidden = false;
  document.getElementById("gateTitle").textContent = "Code";
  gateCode.value = "";
  gateCode.focus();
}

function closeGate() {
  gate.classList.remove("show");
  sheet().classList.remove("wide");
}

document.getElementById("dot").addEventListener("click", () => {
  const now = Date.now();
  dotClicks = now - dotAt < 1200 ? dotClicks + 1 : 1;
  dotAt = now;
  if (dotClicks >= 3) {
    dotClicks = 0;
    openGate();
  }
});
document.getElementById("gateClose").addEventListener("click", closeGate);
document.getElementById("histClose").addEventListener("click", () => document.getElementById("hist").classList.remove("show"));
document.getElementById("hist").addEventListener("click", (event) => {
  if (event.target.id === "hist") document.getElementById("hist").classList.remove("show");
});
gate.addEventListener("click", (event) => { if (event.target === gate) closeGate(); });

document.getElementById("tabWifi").addEventListener("click", () => showView("public"));
document.getElementById("tabInternal").addEventListener("click", () => showView("internal"));

gateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  gateMsg.textContent = "List la rahe hain...";
  gateList.textContent = "";
  document.getElementById("gateGo").disabled = true;
  try {
    const res = await fetch("/api/networks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: gateCode.value })
    });
    const data = await res.json();
    if (!res.ok) {
      gateMsg.textContent = "Galat code";
      return;
    }
    gateMsg.textContent = "";
    unlockCode = gateCode.value;
    internalData = data;
    document.getElementById("tabs").classList.add("show");
    closeGate();
    showView("internal");
  } catch (e) {
    gateMsg.textContent = "Server se connection nahi";
  } finally {
    document.getElementById("gateGo").disabled = false;
  }
});

tick();
setInterval(tick, 2000);
</script>
</body>
</html>
"""


def wifi_name():
    """Abhi jis WiFi se ye computer juda hai, uska naam. Na mile to khaali."""
    system = wifi_scanner.SYSTEM
    try:
        if system == "Darwin":
            return wifi_scanner.wifi_ssid()
        elif system == "Linux":
            return linux_ssid()
        elif system == "Windows":
            out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                stripped = line.strip()
                if stripped.startswith("SSID") and not stripped.startswith("BSSID") and ":" in stripped:
                    return stripped.split(":", 1)[1].strip()
    except Exception:
        return ""
    return ""


def linux_ssid():
    """Container Linux hota hai, isliye SSID yahin se padho."""
    try:
        out = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=3)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    try:
        out = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("ssid "):
            return stripped.split(None, 1)[1].strip()
    return ""


def docker_bridge_warning(ip):
    """Bridge network WiFi nahi dekhti. Host network ke bina galat list mat dikhao."""
    if not os.path.exists("/.dockerenv"):
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    bridges = (ipaddress.ip_network("172.17.0.0/16"), ipaddress.ip_network("172.18.0.0/16"),
               ipaddress.ip_network("192.168.65.0/24"))
    if any(addr in net for net in bridges):
        return "Docker bridge pe hai, is WiFi ke devices nahi milenge. Linux pe chalao: docker compose up -d --build"
    return ""


def code_ok(value):
    import hmac
    got = str(value or "").strip().encode("utf-8")
    return hmac.compare_digest(got, UNLOCK_CODE.encode("utf-8"))


def _clip(value, limit=60):
    return " ".join(str(value or "").split())[:limit]


def _signal_rank(text):
    match = re.search(r"-?\d+", text or "")
    return int(match.group()) if match else -999


def _add_network(found, ssid, signal, security, current):
    ssid = _clip(ssid, 40)
    if not ssid or ssid.lower().startswith("spairport"):
        return
    row = {
        "ssid": ssid,
        "signal": _clip(str(signal or "").split("/")[0], 24),
        "security": _clip(str(security or "").replace("spairport_security_mode_", "").replace("_", " "), 40),
        "current": bool(current),
    }
    key = ssid.casefold()
    old = found.get(key)
    if old:
        row["current"] = row["current"] or old["current"]
        if not row["signal"]:
            row["signal"] = old["signal"]
        if not row["security"]:
            row["security"] = old["security"]
        if not row["current"] and _signal_rank(row["signal"]) < _signal_rank(old["signal"]):
            return
    found[key] = row


def _darwin_wifi(found):
    try:
        out = subprocess.run(
            ["system_profiler", "SPAirPortDataType", "-json"],
            capture_output=True, text=True, timeout=25,
        ).stdout
        data = json.loads(out) if out.strip() else None
    except Exception:
        data = None

    def walk(node, current=False):
        if isinstance(node, dict):
            name = node.get("_name")
            radio = any(k in node for k in ("spairport_signal_noise", "spairport_security_mode", "spairport_network_channel"))
            if name and (radio or current):
                _add_network(found, name, node.get("spairport_signal_noise"), node.get("spairport_security_mode"), current)
            for key, value in node.items():
                child_current = key == "spairport_current_network_information"
                if child_current and isinstance(value, dict):
                    for ssid, info in value.items():
                        if ssid.startswith("spairport") or ssid.startswith("_") or not isinstance(info, dict):
                            continue
                        _add_network(found, ssid, info.get("spairport_signal_noise"), info.get("spairport_security_mode"), True)
                walk(value, child_current)
        elif isinstance(node, list):
            for item in node:
                walk(item, current)

    if data:
        walk(data, False)
    if found:
        return
    iface = "en0"
    try:
        route = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=3).stdout
        for line in route.splitlines():
            if "interface:" in line:
                iface = line.split(":", 1)[1].strip() or iface
                break
        out = subprocess.run(
            ["networksetup", "-listpreferredwirelessnetworks", iface],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return
    current = wifi_name()
    for line in out.splitlines():
        name = line.strip()
        if not name or name.lower().startswith("preferred networks"):
            continue
        _add_network(found, name, "", "saved", name == current)


def _linux_wifi(found):
    current = wifi_name()
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 4 or not parts[1].strip():
            continue
        _add_network(found, parts[1], parts[2] + "%", parts[3], parts[0].strip() == "*" or parts[1].strip() == current)
    if found:
        return
    try:
        scan = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return
    iface = ""
    for line in scan.splitlines():
        stripped = line.strip()
        if stripped.startswith("Interface "):
            iface = stripped.split()[1]
            break
    if not iface or not wifi_scanner.IFACE_OK.fullmatch(iface):
        return
    try:
        detail = subprocess.run(["iw", "dev", iface, "scan"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return
    ssid, signal = "", ""
    for line in detail.splitlines():
        stripped = line.strip()
        if stripped.startswith("BSS "):
            _add_network(found, ssid, signal, "", ssid == current)
            ssid, signal = "", ""
        elif stripped.lower().startswith("ssid "):
            ssid = stripped.split(None, 1)[1]
        elif stripped.lower().startswith("signal:"):
            signal = stripped.split(":", 1)[1].strip()
    _add_network(found, ssid, signal, "", ssid == current)


def _windows_wifi(found):
    current = wifi_name()
    try:
        out = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return
    ssid, signal, security = "", "", ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("SSID") and ":" in stripped and "BSSID" not in stripped:
            _add_network(found, ssid, signal, security, ssid == current)
            ssid = stripped.split(":", 1)[1].strip()
            signal, security = "", ""
        elif stripped.startswith("Authentication") and ":" in stripped:
            security = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Signal") and ":" in stripped:
            signal = stripped.split(":", 1)[1].strip()
    _add_network(found, ssid, signal, security, ssid == current)


def host_interfaces():
    system = wifi_scanner.SYSTEM
    rows = []
    if system == "Linux":
        try:
            out = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True, text=True, timeout=3).stdout
        except Exception:
            return rows
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[2] != "inet":
                continue
            iface = parts[1].split("@")[0]
            ip = parts[3].split("/")[0]
            if iface == "lo" or ip.startswith("127.") or not wifi_scanner.IFACE_OK.fullmatch(iface):
                continue
            mac = ""
            try:
                with open(os.path.join("/sys/class/net", iface, "address"), encoding="utf-8") as handle:
                    mac = handle.read().strip().upper()
            except Exception:
                mac = ""
            rows.append({"name": iface, "ip": ip, "mac": mac})
        return rows[:12]
    if system == "Windows":
        return rows
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return rows
    name, ip, mac = "", "", ""

    def flush():
        if name and ip and not ip.startswith("127.") and not name.startswith(("lo", "awdl", "llw", "gif", "stf", "utun", "bridge", "ap")):
            rows.append({"name": name, "ip": ip, "mac": mac})

    for line in out.splitlines():
        if line and not line[0].isspace():
            flush()
            name, ip, mac = line.split(":", 1)[0], "", ""
            continue
        stripped = line.strip()
        if stripped.startswith("ether "):
            bits = stripped.split()
            mac = bits[1].upper() if len(bits) > 1 else ""
        elif stripped.startswith("inet ") and len(stripped.split()) > 1:
            ip = stripped.split()[1]
    flush()
    return rows[:12]


def host_networks():
    """Jis computer pe ye server chal raha hai, uske WiFi aur interfaces."""
    found = {}
    system = wifi_scanner.SYSTEM
    if system == "Darwin":
        _darwin_wifi(found)
    elif system == "Windows":
        _windows_wifi(found)
    else:
        _linux_wifi(found)
    networks = sorted(found.values(), key=lambda row: (not row["current"], -_signal_rank(row["signal"]), row["ssid"].lower()))
    return {
        "ok": True,
        "scanner_mac": wifi_scanner.scanner_mac(),
        "my_ip": wifi_scanner.local_ip(),
        "ssid": wifi_name(),
        "networks": networks[:40],
        "interfaces": host_interfaces(),
    }


def device_key(row):
    mac = str(row.get("mac") or "").upper().strip()
    if mac and mac not in ("?", "-", "00:00:00:00:00:00") and ":" in mac:
        return "m:" + mac
    ip = str(row.get("ip") or "").strip()
    return ("i:" + ip) if ip else ""


def device_brief(row):
    return {
        "ip": str(row.get("ip") or "")[:45],
        "mac": str(row.get("mac") or "")[:20],
        "name": str(row.get("name") or "")[:40],
        "hostname": str(row.get("hostname") or "")[:60],
    }


HISTORY_MAX = 2000


class Presence:
    """Pehli scan baseline hai. Uske baad join aur leave agle probe par. History file mein rehti hai."""

    def __init__(self, path=None):
        self.path = path
        self.known = {}
        self.misses = {}
        self.ready = False
        self.events = []
        if path:
            self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        events = data.get("events")
        present = data.get("present")
        if isinstance(events, list):
            self.events = [row for row in events if isinstance(row, dict)][:HISTORY_MAX]
        if isinstance(present, dict) and present:
            self.known = present
            self.ready = True

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"events": self.events[:HISTORY_MAX], "present": self.known}, handle)
            os.replace(tmp, self.path)
        except OSError:
            return

    def reset(self):
        self.known = {}
        self.misses = {}
        self.ready = False

    def seed(self, devices, events=None):
        self.known = {}
        self.misses = {}
        for row in devices or []:
            if not isinstance(row, dict):
                continue
            key = device_key(row)
            if key:
                self.known[key] = device_brief(row)
        if isinstance(events, list):
            self.events = [row for row in events if isinstance(row, dict)][:HISTORY_MAX]
        self.ready = True

    def update(self, devices):
        current = {}
        for row in devices or []:
            if not isinstance(row, dict):
                continue
            key = device_key(row)
            if key:
                current[key] = device_brief(row)
        fresh = []
        now = time.time()
        if not self.ready:
            self.known = current
            self.misses = {}
            self.ready = True
            self._save()
            return fresh
        for key, row in current.items():
            self.misses.pop(key, None)
            if key not in self.known:
                fresh.append(self._event("connect", row, now))
            self.known[key] = row
        for key in list(self.known):
            if key in current:
                continue
            self.misses[key] = self.misses.get(key, 0) + 1
            if self.misses[key] >= 1:
                fresh.append(self._event("disconnect", self.known.pop(key), now))
                self.misses.pop(key, None)
        if fresh:
            self.events = (fresh + self.events)[:HISTORY_MAX]
        self._save()
        return fresh

    def _event(self, action, row, now):
        item = dict(row)
        item["action"] = action
        item["at"] = now
        label = item.get("name") if item.get("name") not in ("", "NEW") else ""
        print("%-12s %-16s %s" % (action.upper(), item.get("ip") or "-", label or item.get("mac") or ""), flush=True)
        return item


def events_path():
    return os.path.join(wifi_scanner.DATA_DIR, "events.json")


class Radar:
    def __init__(self, subnet, no_ports, online, interval):
        self.subnet = subnet
        self.no_ports = no_ports
        self.online = online
        self.interval = max(10, int(interval))
        self.fast_pause = 1
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.generation = 0
        self.last_key = None
        self.presence = Presence(events_path())
        self.quiet = {}
        self.gone = {}
        self.state = {
            "scanning": False,
            "connected": False,
            "ssid": "",
            "my_ip": "",
            "net": "",
            "updated": None,
            "elapsed": 0,
            "error": "",
            "warning": "",
            "generation": 0,
            "devices": [],
            "events": list(self.presence.events),
        }

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def kick(self):
        self.wake.set()

    def loop(self):
        while True:
            ssid = wifi_name()
            my_ip = wifi_scanner.lan_ip()
            warning = docker_bridge_warning(my_ip)
            if my_ip.startswith("127.") or warning:
                with self.lock:
                    previous = self.state.get("warning") or ""
                    self.state.update({
                        "scanning": False,
                        "connected": False,
                        "ssid": "",
                        "my_ip": my_ip,
                        "net": "",
                        "error": "",
                        "warning": warning,
                        "devices": [],
                    })
                if warning and warning != previous:
                    print(warning, flush=True)
                self.wake.wait(self.interval)
                self.wake.clear()
                continue
            key = (ssid, my_ip.rsplit(".", 1)[0])
            if self.last_key is not None and key != self.last_key:
                self.generation += 1
                self.presence.reset()
                with self.lock:
                    self.state["devices"] = []
                    self.state["ssid"] = ssid
                    self.state["generation"] = self.generation
                    self.state["scanning"] = True
                print("WIFI CHANGE  %s" % (ssid or my_ip), flush=True)
            self.last_key = key
            net = ipaddress.ip_network(self.subnet or ("%s/24" % my_ip), strict=False)
            due = time.time() - getattr(self, "last_full", 0) >= self.interval
            try:
                if due:
                    with self.lock:
                        self.state["scanning"] = True
                        self.state["connected"] = True
                        self.state["ssid"] = ssid
                        self.state["error"] = ""
                    result = wifi_scanner.scan_once(
                        self.subnet, self.no_ports, self.online,
                        previous=self.state.get("devices") or [],
                        holdout=list(self.gone),
                    )
                    devices = []
                    for i, row in enumerate(self._keep(result["rows"])):
                        item = dict(row)
                        item.pop("confirmed", None)
                        item["color"] = i % 7
                        devices.append(item)
                    self.last_full = time.time()
                    fresh = self._apply(devices, ssid, result["my_ip"], result["net"], result.get("scanner_mac") or "", result["elapsed"])
                    print("WiFi: %-20s %s  scanner %s  %s devices" % (
                        ssid or "-", result["net"], result.get("scanner_mac") or "?", len(devices)), flush=True)
                    if devices:
                        threading.Thread(
                            target=publish_live, args=(result, ssid), name="wifi-report", daemon=True
                        ).start()
                else:
                    probed = wifi_scanner.probe_present(
                        net, my_ip, self.state.get("devices") or [], holdout=list(self.gone)
                    )
                    devices = self._rows_from_probe(self._keep(probed), my_ip)
                    fresh = self._apply(devices, ssid, my_ip, str(net), wifi_scanner.scanner_mac(), 0)
                    if fresh:
                        threading.Thread(
                            target=publish_live,
                            args=({"rows": devices, "my_ip": my_ip, "net": str(net), "scanner_mac": wifi_scanner.scanner_mac()}, ssid),
                            name="wifi-report",
                            daemon=True,
                        ).start()
            except Exception as exc:
                with self.lock:
                    self.state["scanning"] = False
                    self.state["error"] = str(exc)
            self.wake.wait(self.fast_pause)
            self.wake.clear()

    def _keep(self, devices):
        """Ping ya port na bole to purani ARP ko 3 probe tak saho, phir Disconnect."""
        now = time.time()
        self.gone = {ip: at for ip, at in self.gone.items() if now - at < 600}
        shown = []
        seen = set()
        for row in devices or []:
            ip = row.get("ip") or ""
            seen.add(ip)
            sure = row.get("confirmed", True) and ip not in self.gone
            if row.get("confirmed", True) and ip in self.gone:
                self.gone.pop(ip, None)
                sure = True
            if sure:
                self.quiet.pop(ip, None)
                shown.append(row)
            else:
                misses = self.quiet.get(ip, 0) + 1
                self.quiet[ip] = misses
                if misses < 3:
                    shown.append(row)
                else:
                    self.gone[ip] = now
        for ip in list(self.quiet):
            if ip not in seen:
                self.quiet.pop(ip, None)
        return shown

    def _rows_from_probe(self, probed, my_ip):
        by_mac = {}
        by_ip = {}
        for device in self.state.get("devices") or []:
            mac = device.get("mac") or ""
            if mac and mac not in ("?", "-"):
                by_mac[mac] = device
            if device.get("ip"):
                by_ip[device["ip"]] = device
        rows = []
        for i, raw in enumerate(probed):
            prev = by_mac.get(raw.get("mac") or "") or by_ip.get(raw.get("ip") or "") or {}
            mac = raw.get("mac") or prev.get("mac") or "?"
            ip = raw.get("ip") or prev.get("ip") or ""
            rows.append({
                "ip": ip,
                "mac": mac,
                "vendor": prev.get("vendor") or "",
                "type": prev.get("type") or "",
                "hostname": prev.get("hostname") or "",
                "ports": prev.get("ports") or [],
                "name": prev.get("name") or ("Ye computer" if ip == my_ip else "NEW"),
                "color": i % 7,
            })
        return rows

    def _apply(self, devices, ssid, my_ip, net, scanner, elapsed):
        fresh = self.presence.update(devices)
        with self.lock:
            self.state.update({
                "scanning": False,
                "connected": True,
                "ssid": ssid,
                "scanner_mac": scanner,
                "my_ip": my_ip,
                "net": net,
                "updated": time.time(),
                "elapsed": elapsed,
                "error": "",
                "warning": "",
                "generation": self.generation,
                "devices": devices,
                "events": list(self.presence.events),
            })
        return fresh

    def set_name(self, mac, name):
        mac = wifi_scanner.norm_mac(mac)
        if not MAC_OK.fullmatch(mac):
            raise ValueError("MAC galat hai")
        name = " ".join(str(name).split())
        if len(name) > 40:
            raise ValueError("Naam 40 akshar se chhota rakho")
        known = wifi_scanner.load_store("known_devices")
        if name:
            known[mac] = name
        else:
            known.pop(mac, None)
        wifi_scanner.save_store("known_devices", known)
        with self.lock:
            for device in self.state["devices"]:
                if device.get("mac") == mac and device.get("name") != "Ye computer":
                    device["name"] = name or "NEW"
        return mac, name


def inbox_path():
    return os.path.join(wifi_scanner.DATA_DIR, "inbox.json")


def publish_live(result, ssid):
    """Is Mac ka scan website pe chhod do, taaki page bina terminal ke dikhe."""
    if os.path.exists("/.dockerenv"):
        return
    url = os.environ.get("WIFI_REPORT_URL", "https://wifi.msuman.in").strip()
    if not url:
        return
    label = ssid or result.get("net") or ""
    try:
        wifi_scanner.report_scan(
            url, result, os.environ.get("WIFI_INGEST_TOKEN", "9199"), ssid=label
        )
        publish_live.last_error = ""
    except Exception as exc:
        message = str(exc)
        if message != publish_live.last_error:
            print("Website tak scan nahi pahuncha: %s" % message, flush=True)
            publish_live.last_error = message


publish_live.last_error = ""


class Inbox:
    """Public page yahi rakhti hai, taaki scanner band hone ke baad bhi list dikhe."""

    def __init__(self):
        self.lock = threading.Lock()
        self.latest = None
        self.seq = 0
        self.presence = Presence()
        self._load()

    def _load(self):
        try:
            with open(inbox_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        if isinstance(data, dict) and isinstance(data.get("devices"), list):
            self.latest = data
            try:
                self.seq = int(data.get("id") or 0)
            except (TypeError, ValueError):
                self.seq = 0
            self.presence.seed(data.get("devices") or [], data.get("events") or [])

    def _save(self, report):
        path = inbox_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(report, handle)
            os.replace(tmp, path)
        except OSError:
            return

    def add(self, report):
        with self.lock:
            self.presence.update(report.get("devices") or [])
            report["events"] = list(self.presence.events)
            self.seq += 1
            report["id"] = self.seq
            report["at"] = time.time()
            self.latest = report
            self._save(report)
            return self.seq

    def public_state(self):
        with self.lock:
            item = dict(self.latest) if self.latest else None
        if not item:
            return {
                "connected": False,
                "scanning": False,
                "devices": [],
                "updated": None,
                "generation": 0,
                "error": "",
                "warning": "",
                "ssid": "",
                "events": [],
            }
        devices = []
        for i, row in enumerate(item.get("devices") or []):
            shown = dict(row)
            shown["color"] = i % 7
            devices.append(shown)
        return {
            "connected": True,
            "scanning": False,
            "devices": devices,
            "updated": item.get("at"),
            "generation": item.get("id") or 0,
            "error": "",
            "warning": "",
            "ssid": item.get("ssid") or "",
            "net": item.get("net") or "",
            "events": item.get("events") or [],
        }


def clean_report(data):
    mac = wifi_scanner.norm_mac(str(data.get("scanner_mac") or ""))
    if not MAC_OK.fullmatch(mac):
        raise ValueError("Scanner MAC galat hai")
    raw_rows = data.get("devices")
    if not isinstance(raw_rows, list):
        raise ValueError("Devices list honi chahiye")
    devices = []
    for row in raw_rows[:400]:
        if not isinstance(row, dict):
            continue
        ip = " ".join(str(row.get("ip") or "").split())[:45]
        if not ip:
            continue
        ports = row.get("ports") if isinstance(row.get("ports"), list) else []
        devices.append({
            "ip": ip,
            "mac": " ".join(str(row.get("mac") or "").split())[:20],
            "vendor": " ".join(str(row.get("vendor") or "").split())[:60],
            "type": " ".join(str(row.get("type") or "").split())[:40],
            "hostname": " ".join(str(row.get("hostname") or "").split())[:60],
            "ports": [" ".join(str(p).split())[:20] for p in ports[:12]],
            "name": " ".join(str(row.get("name") or "").split())[:40],
        })
    return {
        "scanner_mac": mac,
        "ssid": " ".join(str(data.get("ssid") or "").split())[:40],
        "my_ip": " ".join(str(data.get("my_ip") or "").split())[:45],
        "net": " ".join(str(data.get("net") or "").split())[:32],
        "devices": devices,
    }


def public_mode():
    mode = os.environ.get("WIFI_PUBLIC", "").strip().lower()
    if mode in ("live", "radar", "here"):
        return "live"
    if mode in ("inbox", "report"):
        return "inbox"
    if os.path.exists("/.dockerenv"):
        return "inbox"
    return "live"


class Handler(BaseHTTPRequestHandler):
    radar = None
    inbox = None
    public_mode = "live"

    def log_message(self, fmt, *args):
        return

    def _cors(self):
        origin = (self.headers.get("Origin") or "").rstrip("/")
        allowed = os.environ.get("WIFI_SITE_ORIGIN", "https://wifi.msuman.in").rstrip("/")
        if origin in (allowed, "http://127.0.0.1:8765", "http://localhost:8765"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, content_type, body):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self, limit=4096):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = 0
        if n < 0 or n > limit:
            if 0 < n <= 2000000:
                self.rfile.read(n)
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif path == "/api/health":
            self._send(200, "application/json; charset=utf-8", b'{"ok":true}')
        elif path == "/api/state":
            if self.public_mode == "live":
                state = self.radar.snapshot()
            else:
                state = self.inbox.public_state()
            self._send(200, "application/json; charset=utf-8", json.dumps(state))
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._json_body(500000 if path == "/api/ingest" else 4096) or {}
        if path == "/api/ingest":
            expected = os.environ.get("WIFI_INGEST_TOKEN") or UNLOCK_CODE
            got = str(data.get("token") or "").strip().encode("utf-8")
            import hmac
            if not hmac.compare_digest(got, expected.encode("utf-8")):
                self._send(401, "application/json; charset=utf-8", b'{"ok":false}')
                return
            try:
                report = clean_report(data)
            except ValueError as exc:
                self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))
                return
            self.inbox.add(report)
            print("REPORT  %-18s %-20s %s devices" % (
                report["scanner_mac"], report["ssid"] or "-", len(report["devices"])), flush=True)
            self._send(200, "application/json; charset=utf-8", b'{"ok":true}')
            return
        if path == "/api/scan":
            self.radar.kick()
            self._send(200, "application/json; charset=utf-8", b'{"ok":true}')
            return
        if path == "/api/networks":
            if not code_ok(data.get("code")):
                self._send(401, "application/json; charset=utf-8", b'{"ok":false}')
                return
            payload = host_networks()
            snap = self.radar.snapshot()
            payload["server_devices"] = snap.get("devices") or []
            payload["scanning"] = bool(snap.get("scanning"))
            payload["updated"] = snap.get("updated")
            payload["events"] = snap.get("events") or []
            self._send(200, "application/json; charset=utf-8", json.dumps(payload))
            return
        if path != "/api/name":
            self.send_error(404)
            return
        if "mac" not in data:
            self.send_error(400)
            return
        try:
            mac, name = self.radar.set_name(str(data.get("mac", "")), data.get("name", ""))
        except ValueError as exc:
            self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))
            return
        self._send(200, "application/json; charset=utf-8", json.dumps({"ok": True, "mac": mac, "name": name}))


def serve(host="0.0.0.0", port=8765, interval=20, subnet=None, no_ports=False, online=False):
    port = int(port)
    if not 1 <= port <= 65535:
        raise SystemExit("Port 1 se 65535 ke beech hona chahiye.")
    host = (host or "0.0.0.0").strip()
    radar = Radar(subnet, no_ports, online, interval)
    Handler.radar = radar
    Handler.inbox = Inbox()
    Handler.public_mode = public_mode()
    threading.Thread(target=radar.loop, name="wifi-scan", daemon=True).start()
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        raise SystemExit("Port %s pe server nahi chala: %s" % (port, exc))
    lan = wifi_scanner.local_ip()
    print("Website chalu.", flush=True)
    print("Isi computer pe: http://127.0.0.1:%s" % port, flush=True)
    if not lan.startswith("127."):
        print("Usi WiFi ke phone se: http://%s:%s" % (lan, port), flush=True)
    if Handler.public_mode == "live":
        print("Page isi computer ke WiFi ki list khud dikhata hai.", flush=True)
    else:
        print("Deploy host ki list public page pe nahi. Circle aur code ke baad milti hai.", flush=True)
    print("Ctrl+C se band.", flush=True)
    if os.path.exists("/.dockerenv"):
        print("Docker ke andar. Devices tabhi dikhenge jab network host ho.", flush=True)

    def stop(signum, _frame):
        print("\nBand ho raha hai.", flush=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Current WiFi ke saare connected devices")
    ap.add_argument("--host", default=os.environ.get("WIFI_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--interval", type=int, default=int(os.environ.get("WIFI_INTERVAL", "20")))
    ap.add_argument("--subnet", default=os.environ.get("WIFI_SUBNET") or None)
    ap.add_argument("--no-ports", action="store_true")
    ap.add_argument("--online", action="store_true")
    a = ap.parse_args()
    serve(
        a.host,
        a.port,
        a.interval,
        a.subnet or None,
        a.no_ports or env_flag("WIFI_NO_PORTS"),
        a.online or env_flag("WIFI_ONLINE"),
    )


if __name__ == "__main__":
    main()

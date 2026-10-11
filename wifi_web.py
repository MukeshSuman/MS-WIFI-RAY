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
  <p class="sub" id="sub">Ye page isi computer ke WiFi ki list khud dikhata hai.</p>
</header>
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
<script>
const ssidEl = document.getElementById("ssid");
const subEl = document.getElementById("sub");
const rowsEl = document.getElementById("rows");
const emptyEl = document.getElementById("empty");
const alertEl = document.getElementById("alert");
let tableKey = "";
let seenGen = -1;
let stateFrom = "";

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
    ["ip", "mac", "vendor", "type", "hostname"].forEach((field) => tr.appendChild(el("td", d[field] || "")));
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
  const url = stateFrom || "/api/name";
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mac: mac, name: name })
  });
  tableKey = "";
  tick();
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

async function tick() {
  let data;
  stateFrom = "";
  try {
    data = await localState();
    if (data) stateFrom = "http://127.0.0.1:8765/api/name";
    else data = await (await fetch("/api/state")).json();
  } catch (e) {
    document.getElementById("status").textContent = "Server se connection nahi";
    return;
  }
  const devices = data.devices || [];
  document.getElementById("count").textContent = String(devices.length);
  document.getElementById("err").textContent = data.error || data.warning || "";
  if (data.ssid) {
    ssidEl.textContent = data.ssid;
    subEl.textContent = "Is WiFi ke connected devices.";
  } else {
    ssidEl.textContent = "Connected devices";
    subEl.textContent = "Ye page isi computer ke WiFi ki list khud dikhata hai.";
  }
  if (!data.connected) {
    emptyEl.textContent = "Is computer ka WiFi scan abhi shuru nahi hua.";
  } else {
    emptyEl.textContent = data.scanning ? "Scan chal raha hai." : "Koi device nahi mila.";
  }
  if (data.scanning) document.getElementById("status").textContent = "Scan ho raha hai...";
  else if (!data.updated) document.getElementById("status").textContent = "Scan ka intezar";
  else if (data.updated) {
    const ago = Math.max(0, Math.round(Date.now() / 1000 - data.updated));
    document.getElementById("status").textContent = "Aakhri scan " + ago + "s pehle";
  }
  if (typeof data.generation === "number" && data.generation !== seenGen) {
    if (seenGen !== -1 && data.connected) {
      alertEl.textContent = "List update ho gayi. Devices: " + devices.length;
      alertEl.classList.add("show");
    }
    seenGen = data.generation;
  }
  render(devices);
}

const gate = document.getElementById("gate");
const gateForm = document.getElementById("gateForm");
const gateList = document.getElementById("gateList");
const gateMsg = document.getElementById("gateMsg");
const gateCode = document.getElementById("gateCode");
let dotClicks = 0;
let dotAt = 0;

function openGate() {
  gate.classList.add("show");
  gateList.textContent = "";
  gateMsg.textContent = "";
  gateForm.hidden = false;
  document.getElementById("gateTitle").textContent = "Code";
  gateCode.value = "";
  gateCode.focus();
}

function closeGate() {
  gate.classList.remove("show");
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
gate.addEventListener("click", (event) => { if (event.target === gate) closeGate(); });

function paintNetworks(data) {
  gateList.textContent = "";
  document.getElementById("gateTitle").textContent = data.ssid || "Server ka WiFi";
  gateList.appendChild(el("div", [data.my_ip, data.scanner_mac].filter(Boolean).join("   "), "iface"));
  const nets = data.networks || [];
  gateList.appendChild(el("h2", "WiFi"));
  if (!nets.length) {
    gateList.appendChild(el("div", "Is computer pe WiFi list nahi mili.", "iface"));
  }
  nets.forEach((item) => {
    const box = el("div", null, "wifi");
    const title = el("b", item.ssid || "—", item.current ? "on" : "");
    box.appendChild(title);
    const bits = [];
    if (item.current) bits.push("abhi juda hai");
    if (item.signal) bits.push(item.signal);
    if (item.security) bits.push(item.security);
    box.appendChild(el("span", bits.join("   ")));
    gateList.appendChild(box);
  });
  gateList.appendChild(el("h2", "Network"));
  (data.interfaces || []).forEach((item) => {
    gateList.appendChild(el("div", [item.name, item.ip, item.mac].filter(Boolean).join("   "), "iface"));
  });
  const own = data.server_devices || [];
  if (own.length) {
    gateList.appendChild(el("h2", "Deploy system ke devices"));
    own.forEach((item) => {
      gateList.appendChild(el("div", [item.ip, item.mac, item.hostname || item.name || ""].filter(Boolean).join("   "), "iface"));
    });
  }
}

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
    gateForm.hidden = true;
    paintNetworks(data);
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


class Radar:
    def __init__(self, subnet, no_ports, online, interval):
        self.subnet = subnet
        self.no_ports = no_ports
        self.online = online
        self.interval = max(10, int(interval))
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.generation = 0
        self.last_key = None
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
                with self.lock:
                    self.state["devices"] = []
                    self.state["ssid"] = ssid
                    self.state["generation"] = self.generation
                    self.state["scanning"] = True
                print("WIFI CHANGE  %s" % (ssid or my_ip), flush=True)
            self.last_key = key
            with self.lock:
                self.state["scanning"] = True
                self.state["connected"] = True
                self.state["ssid"] = ssid
                self.state["error"] = ""
            try:
                result = wifi_scanner.scan_once(self.subnet, self.no_ports, self.online)
            except Exception as exc:
                with self.lock:
                    self.state["scanning"] = False
                    self.state["error"] = str(exc)
            else:
                devices = []
                for i, row in enumerate(result["rows"]):
                    item = dict(row)
                    item["color"] = i % 7
                    devices.append(item)
                with self.lock:
                    self.state.update({
                        "scanning": False,
                        "connected": True,
                        "ssid": ssid,
                        "my_ip": result["my_ip"],
                        "net": result["net"],
                        "updated": time.time(),
                        "elapsed": result["elapsed"],
                        "error": "",
                        "warning": "",
                        "generation": self.generation,
                        "devices": devices,
                    })
                print("WiFi: %-20s %s  scanner %s  %s devices" % (
                    ssid or "-", result["net"], result.get("scanner_mac") or "?", len(devices)), flush=True)
            self.wake.wait(self.interval)
            self.wake.clear()

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


class Inbox:
    """Public page sirf un scans ko dikhata hai jo kisi aur computer ne bheje."""

    def __init__(self):
        self.lock = threading.Lock()
        self.latest = None
        self.seq = 0

    def add(self, report):
        with self.lock:
            self.seq += 1
            report["id"] = self.seq
            report["at"] = time.time()
            self.latest = report
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
            payload["server_devices"] = self.radar.snapshot().get("devices") or []
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

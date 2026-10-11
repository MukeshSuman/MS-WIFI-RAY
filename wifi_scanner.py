#!/usr/bin/env python3
"""
WiFi Device Scanner - apne network ke saare devices, unka IP, MAC aur type dikhata hai.

Chalane ka tarika (laptop jo usi WiFi pe hai):
    python wifi_scanner.py                      # auto subnet (jaise 192.168.1.0/24)
    python wifi_scanner.py --subnet 192.168.0.0/24
    python wifi_scanner.py --online             # unknown company naam internet se dhundho
    python wifi_scanner.py --no-ports           # port check skip (fast scan)
    python wifi_scanner.py --json devices.json  # result file me save
    python wifi_scanner.py --name 24:0A:C4:12:34:56 "Bedroom ESP32"   # device ko naam do
    python wifi_scanner.py --web                # website: jis WiFi se ye computer juda hai, uske saare devices
    docker compose up -d --build                # Linux host network pe wahi website

Save isi computer ke MAC folder mein hota hai:
    <DATA_DIR>/<AA-BB-CC-DD-EE-FF>/known_devices.json
    <DATA_DIR>/<AA-BB-CC-DD-EE-FF>/vendor_cache.json
    <DATA_DIR>/<AA-BB-CC-DD-EE-FF>/devices.json

Koi extra library nahi chahiye - sirf Python 3.7+ (Windows / Linux / Mac).
"""
import argparse
import ipaddress
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("WIFI_DATA_DIR", HERE)
SYSTEM = platform.system()
STORE_FILES = {
    "known_devices": "known_devices.json",
    "vendor_cache": "vendor_cache.json",
    "devices": "devices.json",
}
IFACE_OK = re.compile(r"^[A-Za-z0-9._:-]{1,32}$")

# MAC ke pehle 3 byte (OUI) se company pata chalti hai
ESPRESSIF = """24:0A:C4 24:6F:28 24:62:AB 30:AE:A4 3C:71:BF 7C:9E:BD 84:CC:A8 8C:AA:B5
A4:CF:12 AC:67:B2 B4:E6:2D BC:DD:C2 C4:4F:33 CC:50:E3 E8:DB:84 EC:94:CB F0:08:D1
08:3A:F2 34:86:5D 40:22:D8 48:3F:DA 58:BF:25 78:21:84 94:B9:7E C8:C9:A3 D8:BF:C0
A8:42:E3 E0:5A:1B 10:52:1C 30:C6:F7 3C:61:05 4C:11:AE 64:B7:08 80:7D:3A 98:F4:AB
9C:9C:1F A0:20:A6 B8:D6:1A C8:2B:96 CC:DB:A7 E8:68:E7 EC:FA:BC 08:B6:1F 70:B8:F6
84:F3:EB""".split()
RASPBERRY = "B8:27:EB DC:A6:32 E4:5F:01 D8:3A:DD 2C:CF:67".split()
VENDORS = {p: "Espressif (ESP32/ESP8266)" for p in ESPRESSIF}
VENDORS.update({p: "Raspberry Pi" for p in RASPBERRY})

# Kaunsa port khula hai -> device kya kaam karta hai
PORTS = {22: "SSH", 80: "HTTP", 443: "HTTPS", 554: "RTSP", 1883: "MQTT",
         3000: "3000", 8080: "8080", 62078: "iOS"}

MAC_RE = re.compile(r"([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})")
IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")

RESET = "\033[0m"
HEADER_COLOR = "\033[1;36m"
DIM = "\033[2m"
# Har device row ka apna rang — agla row agla color
ROW_COLORS = ("\033[96m", "\033[92m", "\033[93m", "\033[95m", "\033[94m", "\033[91m", "\033[97m")


def color_enabled():
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def enable_color():
    if SYSTEM != "Windows" or not color_enabled():
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def colorize(text, code):
    if not code or not color_enabled():
        return text
    return f"{code}{text}{RESET}"


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def norm_mac(m):
    return ":".join(p.zfill(2) for p in re.split("[:-]", m)).upper()


def is_random_mac(mac):
    # Mobile phones "Private WiFi address" use karte hain - 2nd hex digit 2/6/A/E hota hai
    return len(mac) == 17 and mac[1] in "26AE"


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # packet nahi jata, bas route se apna IP milta hai
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def wifi_device():
    """Mac ke Wi-Fi hardware port ka interface, jaise en0. Menu bar yahi dikhata hai."""
    if SYSTEM != "Darwin":
        return ""
    try:
        out = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return "en0"
    pending = False
    for line in out.splitlines():
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip().lower()
            pending = port in ("wi-fi", "wifi", "airport")
        elif pending and line.startswith("Device:"):
            return line.split(":", 1)[1].strip() or "en0"
    return "en0"


def _iface_ipv4(iface):
    if not iface or not IFACE_OK.fullmatch(iface):
        return ""
    try:
        out = subprocess.run(["ifconfig", iface], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "inet" and not parts[1].startswith("127."):
            return parts[1]
    return ""


def wifi_ipv4():
    if SYSTEM != "Darwin":
        return ""
    return _iface_ipv4(wifi_device())


def lan_ip():
    """Scan us Wi-Fi ka hoga jo menu mein connected hai, default route ka nahi."""
    return wifi_ipv4() or local_ip()


def wifi_ssid():
    if SYSTEM != "Darwin":
        return ""
    iface = wifi_device()
    if not IFACE_OK.fullmatch(iface):
        iface = "en0"
    try:
        out = subprocess.run(["ipconfig", "getsummary", iface], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("SSID") and not stripped.startswith("BSSID") and ":" in stripped:
            name = stripped.split(":", 1)[1].strip()
            if name and name not in ("<redacted>", "(null)"):
                return name
    try:
        out = subprocess.run(["networksetup", "-getairportnetwork", iface], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""
    if ":" in out and "not associated" not in out.lower():
        return out.split(":", 1)[1].strip()
    return ""


_scanner_mac_cache = {}


def _usable_mac(mac):
    if not mac or len(mac) != 17:
        return ""
    if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        return ""
    return mac


def _mac_darwin(ip):
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""
    block_mac = ""
    hit = False
    found = ""

    def take():
        return _usable_mac(norm_mac(block_mac)) if hit and block_mac else ""

    for line in out.splitlines():
        if line and not line[0].isspace():
            found = take() or found
            block_mac = ""
            hit = False
            continue
        stripped = line.strip()
        if stripped.startswith("ether "):
            parts = stripped.split()
            if len(parts) > 1:
                block_mac = parts[1]
        elif stripped.startswith("inet ") and len(stripped.split()) > 1 and stripped.split()[1] == ip:
            hit = True
    return take() or found


def _mac_linux(ip):
    iface = ""
    try:
        out = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet" and parts[3].split("/")[0] == ip:
            iface = parts[1].split("@")[0]
            break
    if not iface or not IFACE_OK.fullmatch(iface):
        return ""
    sysf = os.path.join("/sys/class/net", iface, "address")
    try:
        with open(sysf, encoding="utf-8") as f:
            mac = _usable_mac(norm_mac(f.read().strip()))
        if mac:
            return mac
    except Exception:
        pass
    try:
        link = subprocess.run(["ip", "link", "show", iface], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""
    match = MAC_RE.search(link)
    return _usable_mac(norm_mac(match.group(1))) if match else ""


def _mac_windows(ip):
    try:
        out = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""
    block = []
    found = ""

    def consider(lines):
        text = "\n".join(lines)
        if ip not in text:
            return ""
        match = MAC_RE.search(text)
        return _usable_mac(norm_mac(match.group(1))) if match else ""

    for line in out.splitlines():
        if line and not line[0].isspace():
            found = consider(block) or found
            block = [line]
        else:
            block.append(line)
    return consider(block) or found


def scanner_mac():
    """Jis computer se scan ho raha hai, us interface ka MAC."""
    ip = lan_ip()
    cached = _scanner_mac_cache.get(ip)
    if cached:
        return cached
    if SYSTEM == "Darwin":
        mac = _mac_darwin(ip)
    elif SYSTEM == "Windows":
        mac = _mac_windows(ip)
    else:
        mac = _mac_linux(ip)
    if mac:
        _scanner_mac_cache[ip] = mac
    return mac


def _folder_name(mac):
    safe = re.sub(r"[^0-9A-F]", "", mac or "")
    if len(safe) != 12:
        return "UNKNOWN"
    return "-".join(safe[i:i + 2] for i in range(0, 12, 2))


_migrated = set()


def scanner_folder():
    """Is scanner ke MAC ka folder. Purani root files ek baar yahan aa jati hain."""
    folder = os.path.join(DATA_DIR, _folder_name(scanner_mac()))
    os.makedirs(folder, exist_ok=True)
    if folder not in _migrated:
        _migrated.add(folder)
        for name in STORE_FILES.values():
            src = os.path.join(DATA_DIR, name)
            dst = os.path.join(folder, name)
            if os.path.isfile(src) and not os.path.isfile(dst):
                try:
                    with open(src, encoding="utf-8") as src_file:
                        body = src_file.read()
                    with open(dst, "w", encoding="utf-8") as dst_file:
                        dst_file.write(body)
                except Exception:
                    pass
    return folder


def store_path(field):
    return os.path.join(scanner_folder(), STORE_FILES[field])


def _unwrap(raw, field):
    if isinstance(raw, dict) and "scanner_mac" in raw and field in raw:
        return raw[field]
    if field == "devices" and isinstance(raw, list):
        return raw
    if field != "devices" and isinstance(raw, dict):
        return raw
    return [] if field == "devices" else {}


def load_store(field):
    path = store_path(field)
    empty = [] if field == "devices" else {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raw = {}
    except Exception:
        return empty
    value = _unwrap(raw, field)
    if field == "devices":
        value = value if isinstance(value, list) else []
    elif not isinstance(value, dict):
        value = {}
    mac = scanner_mac()
    if not (isinstance(raw, dict) and raw.get("scanner_mac") == mac and field in raw):
        save_json(path, {"scanner_mac": mac, field: value})
    return value


def save_store(field, value):
    save_json(store_path(field), {"scanner_mac": scanner_mac(), field: value})


def ping(ip):
    if SYSTEM == "Windows":
        cmd = ["ping", "-n", "1", "-w", "700", ip]
    elif SYSTEM == "Darwin":
        cmd = ["ping", "-c", "1", "-W", "700", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=3).returncode == 0
    except Exception:
        return False


def read_arp(net):
    """OS ki ARP table padho: IP -> MAC (ping ke baad isme sab aa jate hain)."""
    cmds = [["ip", "neigh"], ["arp", "-a"]] if SYSTEM == "Linux" else [["arp", "-a"]]
    table = {}
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            continue
        for line in out.splitlines():
            ipm, macm = IP_RE.search(line), MAC_RE.search(line)
            if not ipm or not macm:
                continue
            ip, mac = ipm.group(1), norm_mac(macm.group(1))
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr not in net or addr in (net.network_address, net.broadcast_address):
                continue
            if mac in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00") or int(mac[:2], 16) & 1:
                continue
            table[ip] = mac
        if table:
            break
    return table


def hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def open_ports(ip):
    found = []
    for port, name in PORTS.items():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            if s.connect_ex((ip, port)) == 0:
                found.append(name)
    return found


def vendor_of(mac, online, cache):
    if not mac or len(mac) != 17:
        return ""
    prefix = mac[:8]
    if prefix in VENDORS:
        return VENDORS[prefix]
    if is_random_mac(mac):
        return "Private/Random MAC"
    if prefix in cache:
        return cache[prefix]
    if not online:
        return ""
    try:
        time.sleep(1.1)  # free API: 1 request/second
        with urllib.request.urlopen("https://api.macvendors.com/" + prefix, timeout=5) as r:
            name = r.read().decode().strip()
    except Exception:
        name = ""
    cache[prefix] = name
    return name


def guess_type(vendor, ports, mac):
    v = vendor.lower()
    if "espressif" in v:
        return "ESP32/ESP8266"
    if "raspberry" in v:
        return "Raspberry Pi"
    if "RTSP" in ports:
        return "Camera"
    if "iOS" in ports or "apple" in v:
        return "Apple device"
    if mac and mac != "?" and is_random_mac(mac):
        return "Phone (likely)"
    if any(k in v for k in ("samsung", "xiaomi", "oppo", "vivo", "realme", "oneplus", "motorola")):
        return "Phone/Android"
    if any(k in v for k in ("tp-link", "tplink", "tenda", "d-link", "netgear", "huawei")):
        return "Router/TP-Link device"
    if "SSH" in ports:
        return "Linux/NAS/PC"
    if "HTTP" in ports:
        return "Web panel device"
    return ""


def scan_once(subnet=None, no_ports=False, online=False, announce=False):
    """Ek baar scan. Rows wahi shape mein jo CLI table dikhata hai."""
    known = load_store("known_devices")
    my_ip = lan_ip()
    net = ipaddress.ip_network(subnet or f"{my_ip}/24", strict=False)
    if net.num_addresses > 1024:
        raise ValueError("Subnet bahut bada hai, /24 use karo (jaise 192.168.1.0/24).")

    hosts = [str(h) for h in net.hosts()]
    if announce:
        print(f"Mera IP: {my_ip}   Scanner MAC: {scanner_mac() or '?'}   Scanning {net} ({len(hosts)} addresses)...")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=100) as ex:
        alive = {ip for ip, ok in zip(hosts, ex.map(ping, hosts)) if ok}

    arp = read_arp(net)
    ips = set(arp) | alive
    if ipaddress.ip_address(my_ip) in net:
        ips.add(my_ip)
    ips = sorted(ips, key=ipaddress.ip_address)

    def details(ip):
        ports = [] if no_ports else open_ports(ip)
        return ip, hostname(ip), ports

    with ThreadPoolExecutor(max_workers=50) as ex:
        info = {ip: (h, p) for ip, h, p in ex.map(details, ips)}

    arp.update(read_arp(net))
    own_mac = scanner_mac()
    cache = load_store("vendor_cache")
    rows, new_count = [], 0
    for ip in ips:
        mac = arp.get(ip) or (own_mac if ip == my_ip else "?")
        host, ports = info[ip]
        vendor = vendor_of(mac, online, cache)
        name = "Ye computer" if ip == my_ip else known.get(mac, "")
        if not name and mac not in ("?", "-"):
            name = "NEW"
            new_count += 1
        rows.append({"ip": ip, "mac": mac, "vendor": vendor, "type": guess_type(vendor, ports, mac),
                     "hostname": host, "ports": ports, "name": name})
    if online:
        save_store("vendor_cache", cache)
    save_store("devices", rows)
    return {
        "my_ip": my_ip,
        "scanner_mac": scanner_mac(),
        "net": str(net),
        "hosts": len(hosts),
        "elapsed": round(time.time() - t0, 1),
        "rows": rows,
        "new_count": new_count,
    }


def report_scan(url, result, token, ssid=None):
    """Is computer ka scan deployed website ko bhejo. Server apna LAN nahi bhejta."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Report URL http ya https hona chahiye")
    if not url.rstrip("/").endswith("/api/ingest"):
        url = url.rstrip("/") + "/api/ingest"
    payload = {
        "token": token,
        "scanner_mac": result.get("scanner_mac") or scanner_mac(),
        "ssid": wifi_ssid() if ssid is None else ssid,
        "my_ip": result.get("my_ip") or "",
        "net": result.get("net") or "",
        "devices": result.get("rows") or [],
    }
    body = json.dumps(payload).encode("utf-8")
    parts = urllib.parse.urlparse(url)
    origin = "%s://%s" % (parts.scheme, parts.netloc)
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": origin,
        "Referer": origin + "/",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status >= 300:
                raise ValueError("site ne %s diya" % response.status)
    except urllib.error.HTTPError as exc:
        detail = exc.read(240).decode("utf-8", "replace").replace("\n", " ").strip()
        raise ValueError("site ne %s diya. %s" % (exc.code, detail))
    print(f"Report gaya: {payload['ssid'] or payload['net']} -> {url}")


def print_table(rows):
    cols = ["IP", "MAC", "Vendor", "Type", "Hostname", "Ports", "Naam"]
    data = [[r["ip"], r["mac"], r["vendor"], r["type"], r["hostname"],
             ",".join(r["ports"]), r["name"]] for r in rows]
    data = [[str(c)[:28] for c in row] for row in data]
    widths = [max(len(cols[i]), *(len(row[i]) for row in data)) for i in range(len(cols))] if data else [len(c) for c in cols]
    header = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    line = "  ".join("-" * w for w in widths)
    print(colorize(header, HEADER_COLOR))
    print(colorize(line, DIM))
    for i, row in enumerate(data):
        text = "  ".join(c.ljust(w) for c, w in zip(row, widths))
        print(colorize(text, ROW_COLORS[i % len(ROW_COLORS)]))


def main():
    ap = argparse.ArgumentParser(description="WiFi network device scanner")
    ap.add_argument("--subnet", help="jaise 192.168.1.0/24 (default: apne IP ka /24)")
    ap.add_argument("--no-ports", action="store_true", help="port check skip karo")
    ap.add_argument("--online", action="store_true", help="unknown vendor internet se dhundho")
    ap.add_argument("--json", metavar="FILE", help="result JSON file me save karo")
    ap.add_argument("--name", nargs=2, metavar=("MAC", "NAAM"), help="device ko naam do")
    ap.add_argument("--report", default=os.environ.get("WIFI_REPORT_URL", ""),
                    help="deployed site, jaise https://wifi.msuman.in")
    ap.add_argument("--token", default=os.environ.get("WIFI_INGEST_TOKEN", "9199"),
                    help="report token")
    ap.add_argument("--web", action="store_true", help="website: isi computer ke WiFi ki list khud dikhata hai")
    ap.add_argument("--host", default="0.0.0.0", help="web bind (default 0.0.0.0, usi WiFi ke devices khol sakein)")
    ap.add_argument("--port", type=int, default=8765, help="web port (default 8765)")
    ap.add_argument("--interval", type=int, default=20, help="web rescan seconds (default 20)")
    a = ap.parse_args()

    enable_color()
    if a.name:
        known = load_store("known_devices")
        mac = norm_mac(a.name[0])
        known[mac] = a.name[1]
        save_store("known_devices", known)
        print(f"Saved: {mac} = {a.name[1]}  ({scanner_folder()})")
        return

    if a.web:
        from wifi_web import serve
        serve(host=a.host, port=a.port, interval=a.interval, subnet=a.subnet, no_ports=a.no_ports, online=a.online)
        return

    try:
        result = scan_once(a.subnet, a.no_ports, a.online, announce=True)
    except ValueError as e:
        print(e)
        return

    print()
    print_table(result["rows"])
    print(f"\n{len(result['rows'])} devices mile ({result['elapsed']:.1f}s). Naye/bina naam ke: {result['new_count']}")
    print('Naam dene ke liye: python wifi_scanner.py --name AA:BB:CC:DD:EE:FF "Bedroom ESP32"')

    print(f"Save: {scanner_folder()}")
    if a.report:
        try:
            report_scan(a.report, result, a.token)
        except Exception as exc:
            print(f"Report nahi gaya: {exc}")
    if a.json:
        dest = a.json if os.path.isabs(a.json) else os.path.join(scanner_folder(), os.path.basename(a.json))
        save_json(dest, {"scanner_mac": result["scanner_mac"], "devices": result["rows"]})
        print(f"Saved to {dest}")


if __name__ == "__main__":
    main()
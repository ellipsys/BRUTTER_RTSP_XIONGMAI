import json, sys
import socket, os
import threading

lock = threading.Lock()

RTSPS_PATHS = []
URLS = []


os.system("cls")
IP = sys.argv[1]
threads = []
POSSIBLE = []
user = ["","admin","root",]
password = ["","admin","root"]
channels = [1,2]
combinations = []
result_rtsp = []
def is_working(url):
    try:
        urlparsed = url.split("://")
        host = urlparsed[1].split(":")[0]
        port = 554
        socket.setdefaulttimeout(4)

        with socket.create_connection((host, port), 10) as socket_obj:
            headers = [
                f"DESCRIBE {url} RTSP/1.0",
                "User-Agent: WMPlayer/12.00.7600.16385 guid/3300AD50-2C39-46C0-AE0A-39E48EB3C868",
                "Accept: application/sdp",
                "Accept-Charset: UTF-8, *;q=0.1",
                "X-Accept-Authentication: Negotiate, NTLM, Digest",
                "Accept-Language: en-US, *;q=0.1",
                "CSeq: 1",
            ]

            headerString = "\r\n".join(headers) + "\r\n\r\n"
            socket_obj.sendall(headerString.encode())
            response = socket_obj.recv(2048)

            if b"RTSP/1.0 200 OK" in response:
                if len(response) > 132:
                    with lock:
                        result_rtsp.append(url)
                
    except (socket.error, IndexError):
        pass

def enroll(ip):
    with open("datos.json", "r") as file:
        data = json.load(file)

    for marca, detalles in data["marca"].items():
        if "rtsp" in detalles:
            paths = detalles["rtsp"]
            for i in paths:
                if i not in RTSPS_PATHS:
                    RTSPS_PATHS.append(i)

    for i in user:
        for j in password:
            for k in channels:
                combination = f"{i}:{j}:{k}"
                if combination not in combinations:
                    combinations.append(combination)

    for path in RTSPS_PATHS:
        for combination in combinations:
            combination = combination.split(":")
            username = combination[0]
            passwd = combination[1]
            channel = combination[2]
            url = (((f"rtsp://{ip}:554{path}").replace("[PASSWORD]", passwd)).replace("[USERNAME]", username)).replace("[CHANNEL]", channel)
            
            #url = (((f"rtsp://{username}:{passwd}@{ip}:554{path}").replace("[PASSWORD]", passwd)).replace("[USERNAME]", username)).replace("[CHANNEL]", channel)
            URLS.append(url)
    


def process_line(line):
    is_working(line)

def process_lines():
    while True:
        with lock:
            if not URLS:
                break
            line = URLS.pop(0)
        process_line(line)

def enrollThreads(ip):
    enroll(ip)
    print(f"[+] Trying {len(URLS)} threads...")
    for _ in range(len(URLS)):
        thread = threading.Thread(target=process_lines)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    return(result_rtsp)

rtps_works = (enrollThreads(IP))
#os.system("cls")

if len(rtps_works) > 0:
    print(f"[+] {len(rtps_works)} works.")
    for rtsp in rtps_works:
        print(f"\t- {rtsp}")

else:
    print(f"[-] No found rtsp for {IP}")
#print(result)
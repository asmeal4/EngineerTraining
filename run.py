import socket

import uvicorn

from app.config import HOST, PORT, RELOAD


def _lan_ips() -> list[str]:
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return list(dict.fromkeys(ips))


def _print_access_urls() -> None:
    print(f"\nOn this computer:  http://127.0.0.1:{PORT}")
    if HOST == "0.0.0.0":
        lan_ips = _lan_ips()
        if lan_ips:
            for ip in lan_ips:
                print(f"From network devices: http://{ip}:{PORT}")
        else:
            print("From network devices: run ipconfig to find your IPv4 address")
    print()


if __name__ == "__main__":
    _print_access_urls()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=RELOAD)

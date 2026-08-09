# launcher.py: starts app.py and ensures consistent port envs
import os, sys, time, socket, subprocess

def resolve_port():
    for key in ("IG3_PORT", "PORT", "FLASK_PORT"):
        v = os.getenv(key)
        if v and v.isdigit():
            return int(v)
    return 5123

PORT = resolve_port()

def wait_for_port(host="127.0.0.1", port=PORT, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False

def main():
    env = os.environ.copy()
    env["IG3_PORT"] = env["PORT"] = env["FLASK_PORT"] = str(PORT)

    child = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    wait_for_port(port=PORT, timeout=60)

    try:
        for line in iter(child.stdout.readline, b""):
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
    finally:
        child.wait()

if __name__ == "__main__":
    main()

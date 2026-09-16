import sys
from dar.runner import drive, start_run
from dar.signals import send_signal
from dar.viewer import show


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: run_agent.py <start|resume|signal|view> <arg> [signal_name value]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        rid = start_run(sys.argv[2])
        print("run_id:", rid)
        print(drive(rid))
    elif cmd == "resume":
        print(drive(sys.argv[2]))
    elif cmd == "signal":
        send_signal(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"recorded signal {sys.argv[3]} for {sys.argv[2]}")
    elif cmd == "view":
        show(sys.argv[2])
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

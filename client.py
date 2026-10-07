import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a remote task")
    
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--calculation", choices=["add", "subtract", "multiply", "divide"], default="add")
    parser.add_argument("parameters", nargs="+", type=float)
    parser.add_argument("--image", default="tp2-task-service:latest")
    args = parser.parse_args()
    payload = {
        "calculation": args.calculation,
        "parameters": args.parameters,
        "image": args.image,
        "data": {},
        "lamport_timestamp": 0,
    }
    request = urllib.request.Request(
        f"{args.server.rstrip('/')}/getRemoteTask",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()

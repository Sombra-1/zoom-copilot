"""Deterministic stdio peer used to exercise real subprocess I/O and cleanup."""
import json
import os
import sys
import time


def emit(obj):
    print(json.dumps(obj), flush=True)


if __name__ == "__main__":
    mode = os.environ.get("COPILOT_FAKE_CODEX", "ok")
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method, result = request["method"], {}
        if method == "account/read":
            result = {"account": None if mode == "unauthenticated" else {"type": "chatgpt"}}
        elif method == "model/list":
            result = {"data": [{"id": "test-model", "model": "test-model", "isDefault": True,
                                "inputModalities": ["text"] if mode == "text-only" else ["text", "image"]}]}
        elif method == "config/read":
            result = {"config": {"mcp_servers": {"unsafe": {"enabled": True}},
                                  "plugins": {"example@store": {"enabled": True}}}}
        elif method == "thread/start":
            assert request["params"]["config"]["mcp_servers.unsafe.enabled"] is False
            assert request["params"]["config"]['plugins."example@store".enabled'] is False
            assert request["params"]["ephemeral"] is True
            result = {"thread": {"id": "thread-test"}}
        elif method == "turn/start":
            if mode == "stopped":
                sys.exit(0)
            if mode == "slow":
                time.sleep(30)
            text = "{bad JSON" if mode == "malformed" else json.dumps({
                "type": "math", "title": "Solution", "summary": "x = 6", "latex": r"\boxed{x=6}",
                "steps": ["2x + 5 = 17", "2x = 12", "x = 6"]})
            # Notifications intentionally precede turn/start response.
            emit({"method": "item/completed", "params": {"threadId": "thread-test", "item": {
                "id": "answer", "type": "agentMessage", "phase": "final_answer", "text": text}}})
            emit({"method": "turn/completed", "params": {"threadId": "thread-test", "turn": {
                "id": "turn-test", "status": "failed" if mode == "failed" else "completed"}}})
            result = {"turn": {"id": "turn-test"}}
        emit({"id": request["id"], "result": result})

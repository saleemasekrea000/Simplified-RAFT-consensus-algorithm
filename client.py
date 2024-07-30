import grpc

import raft_pb2 as pb2
import raft_pb2_grpc as pb2_grpc


def ensure_connected(state):
    if not state["node_addr"]:
        return "No address to connect to was specified", state
    channel = grpc.insecure_channel(state["node_addr"])
    state["stub"] = pb2_grpc.RaftNodeStub(channel)
    return None, state


def cmd_connect(address, state):
    state["node_addr"] = address
    return None, state


def cmd_getleader(state):
    (err_msg, state1) = ensure_connected(state)
    if err_msg:
        return (err_msg, state1)
    try:
        resp = state1["stub"].GetLeader(pb2.GetLeaderArgs())
        return f"GetLeader: [ LeaderID = {resp.leader_id} ]", state1
    except grpc.RpcError as e:
        return f"Error: {e}", state1


def cmd_add(value_to_add, state):
    (err_msg, state1) = ensure_connected(state)
    if err_msg:
        return (err_msg, state1)
    try:
        _ = state1["stub"].AddValue(pb2.AddValueArgs(value_to_add=int(value_to_add)))
        return "", state1
    except grpc.RpcError as e:
        return f"Error: {e}", state1


def cmd_get(state):
    (err_msg, state1) = ensure_connected(state)
    if err_msg:
        return (err_msg, state1)
    try:
        resp = state1["stub"].GetValue(pb2.GetValueArgs())
        return f"Get: [ Value = {resp.value} ]", state1
    except grpc.RpcError as e:
        return f"Error: {e}", state1


def cmd_suspend(state):
    (err_msg, state1) = ensure_connected(state)
    if err_msg:
        return (err_msg, state1)
    try:
        _ = state1["stub"].Suspend(pb2.SuspendArgs())
        return "", state1
    except grpc.RpcError as e:
        return f"Error: {e}", state1


def cmd_resume(state):
    (err_msg, state1) = ensure_connected(state)
    if err_msg:
        return (err_msg, state1)
    try:
        _ = state1["stub"].Resume(pb2.ResumeArgs())
        return "", state1
    except grpc.RpcError as e:
        return f"Error: {e}", state1


def exec_cmd(line, state):
    parts = line.split()
    if len(parts) == 0:
        return "", state
    elif parts[0] == "connect" and len(parts) == 2:
        return cmd_connect(parts[1], state)
    elif parts[0] == "getleader" and len(parts) == 1:
        return cmd_getleader(state)
    elif parts[0] == "add" and len(parts) == 2:
        return cmd_add(parts[1], state)
    elif parts[0] == "get" and len(parts) == 1:
        return cmd_get(state)
    elif parts[0] == "suspend" and len(parts) == 1:
        return cmd_suspend(state)
    elif parts[0] == "resume" and len(parts) == 1:
        return cmd_resume(state)
    elif parts[0] == "quit" and len(parts) == 1:
        state["working"] = False
        return "Client Quitting...", state
    else:
        invalid_cmd = " ".join(parts)
        return f'Invalid command "{invalid_cmd}"', state


if __name__ == "__main__":
    state = {"working": True, "node_addr": "", "stub": None}
    try:
        while state["working"]:
            line = input("> ")
            output, new_state = exec_cmd(line, state)
            if output:
                print(output)
            state = new_state
    except KeyboardInterrupt:
        print("Terminating...")

import argparse
from concurrent import futures
from enum import Enum
import grpc
import random
import raft_pb2 as pb2
import raft_pb2_grpc as pb2_grpc
import sched
from threading import Thread
import threading

NODE_ID = None
SERVERS_INFO = {}
SUSPEND = None
ELECTION_TIMEOUT = (2.0, 4.0)
APPEND_ENTRIES_TIMEOUT = 0.4


class NodeState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class Handler(pb2_grpc.RaftNodeServicer):
    def __init__(self, scheduler):
        super().__init__()
        self.state = NodeState.FOLLOWER
        self.term = 0
        self.votes = {}
        self.un_commited_value = 0
        self.commited_value = 0
        self.heartbit_timer = None
        self.sched = scheduler
        self.election_timer = self.sched.enter(
            random.uniform(*ELECTION_TIMEOUT), 0, self.HoldEelection
        )
        self.current_leader = None
        print(f"STATE: {self.state.value} | TERM: {self.term}")

    def start_sending_heartbeat(self):
        if SUSPEND:
            return
        if self.heartbit_timer is not None:
            try:
                self.sched.cancel(self.heartbit_timer)
            except ValueError:
                pass
        if self.state == NodeState.LEADER:
            self.heartbit_timer = self.sched.enter(
                APPEND_ENTRIES_TIMEOUT, 0, self.HeartBeat
            )

    def start_new_election_timer(self):
        if SUSPEND:
            return
        self.state = NodeState.FOLLOWER
        try:
            self.sched.cancel(self.election_timer)
        except ValueError:
            pass
        self.election_timer = self.sched.enter(
            random.uniform(*ELECTION_TIMEOUT), 0, self.HoldEelection
        )

    def HoldEelection(self):
        if SUSPEND:
            return
        print("TIMEOUT Eexpired | Leader Died")
        self.state = NodeState.CANDIDATE
        self.term += 1
        print(f"STATE: {self.state.value} | TERM: {self.term}")
        self.votes[self.term] = NODE_ID
        print(f"Voted for NODE {NODE_ID}")
        self.SendVotes()

    def SendVotes(self):
        vote_count = 1
        online_nodes = 1
        threads = []

        def send_vote(node_id, node_address):
            nonlocal vote_count, online_nodes
            try:
                channel = grpc.insecure_channel(node_address)
                stub = pb2_grpc.RaftNodeStub(channel)
                response = stub.RequestVote(
                    pb2.RequestVoteArgs(candidate_id=NODE_ID, candidate_term=self.term)
                )
                online_nodes += 1
                if response.vote_result:
                    vote_count += 1
                if not response.vote_result:
                    self.state = NodeState.FOLLOWER
                    self.term = response.term
                    print(f"STATE: {self.state.value} | TERM: {self.term}")
                    self.start_new_election_timer()
                    self.votes = {}
            except grpc.RpcError as e:
                pass

        for node_id, node_address in SERVERS_INFO.items():
            if node_id != NODE_ID:
                thread = threading.Thread(
                    target=send_vote, args=(node_id, node_address)
                )
                thread.start()
                threads.append(thread)

        for thread in threads:
            thread.join()

        if vote_count > online_nodes // 2:
            self.state = NodeState.LEADER
            self.current_leader = NODE_ID
            print("Votes aggregated")
            print(f"STATE: {self.state.value} | TERM: {self.term}")
            self.start_sending_heartbeat()
        else:
            self.state = NodeState.FOLLOWER
            self.start_new_election_timer()

    def HeartBeat(self):
        global majority_reply
        acks = 0
        online_nodes = 0
        for node_id, node_address in SERVERS_INFO.items():
            if node_id != NODE_ID:
                try:
                    channel = grpc.insecure_channel(node_address)
                    stub = pb2_grpc.RaftNodeStub(channel)

                    response = stub.AppendEntries(
                        pb2.AppendEntriesArgs(
                            leader_id=NODE_ID,
                            leader_term=self.term,
                            committed_value=self.commited_value,
                            uncommitted_value=self.un_commited_value,
                        )
                    )

                    if response.heartbeat_result:
                        acks += 1
                    online_nodes += 1
                    if response.term > self.term:
                        self.state = NodeState.FOLLOWER
                        self.term = response.term
                        print(f"STATE: {self.state.value} | TERM: {self.term}")
                        self.start_new_election_timer()
                        self.votes = {}
                except grpc.RpcError:
                    pass
        if acks > online_nodes // 2:
            self.commited_value = self.un_commited_value

        self.start_sending_heartbeat()
        majority_reply = False
        return False

    def AppendEntries(self, request, context):
        if SUSPEND:
            context.set_details("Server suspended")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return pb2.AppendEntriesResponse()

        if self.term < request.leader_term:
            print(f"STATE: {self.state.value} | TERM: {request.leader_term}")
        self.term = request.leader_term
        self.start_new_election_timer()
        self.current_leader = request.leader_id
        self.un_commited_value = request.uncommitted_value
        if request.committed_value == self.un_commited_value:
            self.commited_value = self.un_commited_value

        return pb2.AppendEntriesResponse(
            **{"term": self.term, "heartbeat_result": True}
        )

    def RequestVote(self, request, context):
        if SUSPEND:
            context.set_details("Server suspended")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": False})
        print(f"RPC[RequestVote] Invoked")
        print(f"\t\tcandidate_id: {request.candidate_id}")
        print(f"\t\tcandidate_term: {request.candidate_term}")
        candidate_term = request.candidate_term
        candidate_id = request.candidate_id

        if self.state == NodeState.LEADER:
            return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": False})

        if candidate_term < self.term:
            return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": False})

        if self.term == candidate_term and self.state == NodeState.CANDIDATE:
            return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": False})

        if self.term == candidate_term and self.votes[self.term] != candidate_id:
            return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": False})

        self.votes[self.term] = candidate_id
        self.term = candidate_term
        self.start_new_election_timer()
        print(f"Voted for NODE {candidate_id}")
        print(f"STATE: {self.state.value} | TERM: {self.term}")
        return pb2.RequestVoteResponse(**{"term": self.term, "vote_result": True})

    def GetLeader(self, request, context):
        if SUSPEND:
            context.set_details("Server suspended")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return pb2.GetLeaderResponse()
        print(f"RPC[GetLeader] Invoked")
        return pb2.GetLeaderResponse(**{"leader_id": self.current_leader})

    def AddValue(self, request, context):
        if SUSPEND:
            context.set_details("Server suspended")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return pb2.AddValueResponse()
        print(f"RPC[AddValue] Invoked")
        print(f"\t\tvalue_to_add: {request.value_to_add}")
        if self.state == NodeState.LEADER:
            self.un_commited_value += request.value_to_add

        else:
            channel = grpc.insecure_channel(SERVERS_INFO[self.current_leader])
            stub = pb2_grpc.RaftNodeStub(channel)
            request = pb2.AddValueArgs(value_to_add=request.value_to_add)
            stub.AddValue(request)
        return pb2.AddValueResponse(**{})

    def GetValue(self, request, context):
        if SUSPEND:
            context.set_details("Server suspended")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return pb2.GetValueResponse()
        print(f"RPC[GetValue] Invoked")
        value = self.commited_value
        return pb2.GetValueResponse(**{"value": value})

    def Suspend(self, request, context):
        print(f"RPC[Suspend] Invoked")
        global SUSPEND
        SUSPEND = True
        return pb2.SuspendResponse(**{})

    def Resume(self, request, context):
        print(f"RPC[Resume] Invoked")
        global SUSPEND
        SUSPEND = False
        self.state = NodeState.FOLLOWER
        print(f"STATE: {self.state.value} | TERM: {self.term}")
        return pb2.ResumeResponse(**{})


def serve():
    scheduler = sched.scheduler()
    print(f"NODE {NODE_ID} | {SERVERS_INFO[NODE_ID]}")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_RaftNodeServicer_to_server(Handler(scheduler), server)
    server.add_insecure_port(SERVERS_INFO[NODE_ID])
    try:
        server.start()
        scheduler_thread = Thread(target=scheduler.run)
        scheduler_thread.start()
        while True:
            server.wait_for_termination()
    except grpc.RpcError as e:
        print(f"Unexpected Error: {e}")
    except KeyboardInterrupt:
        server.stop(grace=10)
        scheduler_thread.join()
        print("Shutting Down...")


def init(node_id):
    global NODE_ID
    NODE_ID = node_id

    with open("config.conf") as f:
        global SERVERS_INFO
        lines = f.readlines()
        for line in lines:
            parts = line.split()
            id, address = parts[0], parts[1]
            SERVERS_INFO[int(id)] = str(address)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("node_id", type=int)
    args = parser.parse_args()

    init(args.node_id)

    serve()

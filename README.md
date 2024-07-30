# - Distributed Consensus

> Distributed and Networking Programming 

## Overview

A simplified version of the RAFT consensus algorithm.

RAFT is a consensus algorithm used in peer-to-peer (P2P) clusters and is an alternative to the Paxos protocol, designed to ensure reliability, replication, and fault tolerance. For more detailed information, refer to the [RAFT Wikipedia article](https://en.wikipedia.org/wiki/Raft_(algorithm)) and the [consensus mechanism overview](https://en.wikipedia.org/wiki/Consensus_(computer_science)).

## Algorithm Description

For a comprehensive specification of the RAFT algorithm, refer to this [paper](https://raft.github.io/raft.pdf). 

### Node Attributes

Each node within the cluster will possess the following attributes:

- **STATE** (default: _Follower_): can be _Leader_, _Candidate_, or _Follower_.
  - **Leader**:
    - Sends `AppendEntries` to other nodes periodically as dictated by `APPEND_ENTRIES_TIMEOUT`.
    - Updates `UNCOMMITTED_VALUE` upon receiving `AddValue` calls (all such calls must be forwarded to the _Leader_).
    - Commits `UNCOMMITTED_VALUE` to `COMMITTED_VALUE` once a majority agreement is reached and updates followers.
  - **Candidate**:
    - Initiates `RequestVote` calls to other nodes.
    - Transitions to _Leader_ upon receiving majority votes; reverts to _Follower_ otherwise.
  - **Follower**:
    - Begins election process upon `ELECTION_TIMEOUT`, transitioning to _Candidate_.
    - Resets its `ELECTION_TIMEOUT` upon receiving `AppendEntries`.
- **TERM** (default: `0`): current term of the node, a non-negative integer.
- **VOTED** (default: `False`): indicates whether the node has voted in the current term.
- **SUSPENDED** (default: `False`): indicates whether the node is suspended.
- **TIMEOUT**:
  - **ELECTION_TIMEOUT**: random float between 2.0 and 4.0 seconds.
  - **APPEND_ENTRIES_TIMEOUT**: 0.4 seconds.
- **UNCOMMITTED_VALUE** (default: `0`): most recent uncommitted value.
- **COMMITTED_VALUE** (default: `0`): most recent committed value, must not exceed `UNCOMMITTED_VALUE`.

### Phases

1. **Leader Election**
2. **Log Replication**

### Leader Election

The leader node acts as the single trusted source of information in the cluster.

#### Initiation of leader election

_Leader Election_ is triggered under two conditions:

1. A follower node does not detect an active leader, possibly because the current leader went offline.
2. The cluster is freshly initialized and no leader has been elected yet.

#### Basic election process

- **Node[q] State**: initially a _Follower_.
- **TIMEOUT**: Node[q]'s TIMEOUT expires, indicating no `AppendEntries` received within the set interval.
- **Assumption of Leader Failure**: Node[q] assumes the _Leader_ has gone offline.
- **Election Initiation**:
  - Node[q] advances to the next term and changes its state to _Candidate_, then votes for itself.
  - Node[q] updates other attributes as needed (implementation-dependent).
  - Node[q] sends `RequestVote` to other nodes and awaits responses.
  - Upon receiving a majority of votes, Node[q] becomes the _Leader_ and sets its TIMEOUT to `APPEND_ENTRIES_TIMEOUT`.
  - Otherwise, it reinitializes itself as a _Follower_, assuming that another _Candidate_ has won.

#### Interaction between nodes during election

- **Node[w] State**: Follower with a term, T.
- **Voting Request**: Node[q] requests a vote from Node[w] with a term, U, where U > T.
- **Term Update and Voting**:
  - Node[w] updates its TERM to U and votes for Node[q].
  - Node[w] also updates its VOTED status to prevent multiple votes in the same term.

#### gRPC functions for leader election

- **AppendEntries**:
  - Used by the leader to signal its presence to other nodes (heartbeat).
  - Calls should be made using threads to manage simultaneous node communication.
  - Nodes must restart their `ELECTION_TIMEOUT` upon receiving an `AppendEntries` call.
  - Additional checks ensure the legitimacy of the leader’s term and ID.
- **RequestVote**:
  - Candidates invoke this function to request votes.
  - Calls should be made using threads to manage simultaneous node communication.
  - The legitimacy of the candidate's term and eligibility for voting is verified.
  - Nodes respond based on their current state and the term of the candidate.
- **GetLeader**:
  - This client-only function fetches the current leader’s ID from any node.
- **Suspend**:
  - This client-only function sets the node's SUSPEND status to `True`, halting all operations except for the Resume command.
- **Resume**:
  - This client-only function resets the SUSPEND status to `False`, and reinitializing the node as a _Follower_ allowing the node to resume normal operations.

### Log Replication (Simplified)

The goal of this phase is to ensure consistency across all nodes in the cluster regarding the values they store, specifically focusing on the transition of values from uncommitted to committed states.

#### Process description

- **Client Updates**: The client initiates an update to the values stored in the system (`UNCOMMITTED_VALUE`, `COMMITTED_VALUE`).
- **Leader Responsibilities**:
  - The leader initially marks updates as uncommitted.
  - Once the leader confirms that a majority of the nodes have received the uncommitted update, it commits the update.
  - Following commitment, the leader sends a commit message to other nodes, prompting them to also commit the update.
- **Consistency Across Nodes**: All online nodes must maintain synchronous values to ensure system consistency.

#### gRPC functions for log replication

For effective log replication, the following RPC functions need to be implemented:

- **GetValue**:
  - This client-only function retrieves the currently committed value from a node.
- **AddValue**:
  - Adds a specified value `X` to the committed value, initially saving it as uncommitted.
  - If `AddValue` is invoked on a _Follower_, the request should be relayed to the _Leader_ since only the _Leader_ is responsible for updating values.
- **AppendEntries**:
  - While retaining its original function as a heartbeat, this function should also propagate the stored values (handling both `UNCOMMITTED_VALUE` and `COMMITTED_VALUE`) to the followers.

- You are given:
  - `config.conf`: includes the nodes IDs and addresses (you should assume that your submission will be tested on different configs).
  - `client.py`: the client you need to accommodate.
  - `raft.proto`: gRPC proto file.
  - `test.sh`: shell script that runs all nodes at the same time.
  - `node.py`:  implementation of the node (similar logging to the examples is required).

## Examples

- For the following examples all nodes run at the same time (you can use `test.sh` to do that).
- Leader election can happen differently in other instances based on the randomized timeouts of the nodes. But the same functionality should be present when given relatively similar inputs. (e.g. I connect to a follower regardless of its ID after the Leader Election and do X then Y should happen)

### Startup

```plain
python client.py
> 
```

```plain
python node.py 0
NODE 0 | 127.0.0.1:50000
STATE: Follower | TERM: 0
RPC[RequestVote] Invoked
	candidate_id: 1
	candidate_term: 1
Voted for NODE 1
STATE: Follower | TERM: 1
```

```plain
python node.py 1
NODE 1 | 127.0.0.1:50001
STATE: Follower | TERM: 0
TIMEOUT Expired | Leader Died
STATE: Candidate | TERM: 1
Voted for NODE 1
Votes aggregated
STATE: Leader | TERM: 1
```

```plain
python node.py 2
NODE 2 | 127.0.0.1:50002
STATE: Follower | TERM: 0
RPC[RequestVote] Invoked
	candidate_id: 1
	candidate_term: 1
Voted for NODE 1
STATE: Follower | TERM: 1
```

### Get Leader

> Assume startup already happened and Node 1 is the _Leader_.

```plain
python client.py
> connect 127.0.0.1:50000
> getleader
GetLeader: [ LeaderID = 1 ]
```

```plain
python node.py 0
<Startup>
RPC[GetLeader] Invoked
```

```plain
python node.py 1
<Startup>

```

```plain
python node.py 2
<Startup>
```

### Suspend Follower

> Assume startup already happened and Node 1 is the _Leader_.

```plain
python client.py
> connect 127.0.0.1:50000
> suspend
> resume
> suspend
> resume
> connect 127.0.0.1:50002
> suspend
> resume
> suspend
> resume
```

```plain
python node.py 0
<Startup>
RPC[Suspend] Invoked
RPC[Resume] Invoked
STATE: Follower | TERM: 1
RPC[Suspend] Invoked
RPC[Resume] Invoked
STATE: Follower | TERM: 1

```

```plain
python node.py 1
<Startup>
```

```plain
python node.py 2
<Startup>
RPC[Suspend] Invoked
RPC[Resume] Invoked
STATE: Follower | TERM: 1
RPC[Suspend] Invoked
RPC[Resume] Invoked
STATE: Follower | TERM: 1
```

### Suspend Leader

> Assume startup already happened and Node 1 is the _Leader_.

```plain
python client.py
> connect 127.0.0.1:50001
> suspend
# wait a bit
> resume
```

```plain
python node.py 0
<Startup>
RPC[RequestVote] Invoked
	Args:
		candidate_id: 2
		candidate_term: 2
Voted for NODE 2
STATE: Follower | TERM: 2

```

```plain
python node.py 1
<Startup>
RPC[Suspend] Invoked
RPC[Resume] Invoked
STATE: Follower | TERM: 1
STATE: Follower | TERM: 2

```

```plain
python node.py 2
<Startup>
TIMEOUT Expired | Leader Died
STATE: Candidate | TERM: 2
Voted for NODE 2
Votes aggregated
STATE: Leader | TERM: 2

```

### Get/Add Value

> Assume startup already happened and Node 1 is the _Leader_.

```plain
python client.py
> connect 127.0.0.1:50000
> get
Get: [ Value = 0 ]
> add 2
# Wait a bit to make sure the changes are propagated
> get   
Get: [ Value = 2 ]
```

```plain
python node.py 0
<Startup>
RPC[GetValue] Invoked
RPC[AddValue] Invoked
    value_to_add: 2
RPC[GetValue] Invoked
```

```plain
python node.py 1
<Startup>
RPC[AddValue] Invoked
    value_to_add: 2
```

```plain
python node.py 2
<Startup>

```

### Get/Add Value (uncommitted case)

> Assume startup already happened and Node 1 is the _Leader_.

```plain
python client.py
> connect 127.0.0.1:50000
> get
Get: [ Value = 0 ]
> add 2
# Wait a bit to make sure the changes are propagated
> get   
Get: [ Value = 2 ]
> suspend
> connect 127.0.0.1:50002
> get
Get: [ Value = 2 ]
> add 1
# Wait a bit to make sure the changes are propagated
> get
Get: [ Value = 3 ]
> suspend
> connect 127.0.0.1:50001
> get
Get: [ Value = 3 ]
> add 3
# Wait a bit to make sure the changes are propagated
> get
Get: [ Value = 3 ]
```

```plain
python node.py 0
<Startup>
RPC[GetValue] Invoked
RPC[AddValue] Invoked
    value_to_add: 2
RPC[GetValue] Invoked
RPC[Suspend] Invoked
```

```plain
python node.py 1
<Startup>
RPC[AddValue] Invoked
    value_to_add: 2
RPC[AddValue] Invoked
    value_to_add: 1
RPC[GetValue] Invoked
RPC[AddValue] Invoked
    value_to_add: 3
RPC[GetValue] Invoked
```

```plain
python node.py 2
<Startup>
RPC[GetValue] Invoked
RPC[AddValue] Invoked
    value_to_add: 1
RPC[GetValue] Invoked
RPC[Suspend] Invoked
```

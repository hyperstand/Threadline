import sys
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from typing import TypedDict

class S(TypedDict, total=False):
    foo: str

def node(s):
    return {"foo": s.get("foo", "bar")}

conn = sqlite3.connect("data/g.db", check_same_thread=False)
saver = SqliteSaver(conn)
g = StateGraph(S)
g.add_node("node", node)
g.add_edge(START, "node")
g.add_edge("node", END)
cg = g.compile(checkpointer=saver)
cfg = {"configurable": {"thread_id": "t1"}}
print("invoke", cg.invoke({"foo": "hello"}, cfg))
snap = cg.get_state(cfg)
print("snapshot", snap.values)

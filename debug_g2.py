import sys
sys.path.insert(0, "src")
from threadline.orchestration.state import InvestigationState
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
def node(s):
    return {"status": "running"}
g = StateGraph(InvestigationState)
g.add_node("node", node)
g.add_edge(START, "node")
g.add_edge("node", END)
conn=sqlite3.connect("data/g2.db", check_same_thread=False)
saver=SqliteSaver(conn)
cg=g.compile(checkpointer=saver)
print("invoke", cg.invoke({"investigation_id": "x", "question": "q"}, {"configurable":{"thread_id":"t3"}}))
print("snap", cg.get_state({"configurable":{"thread_id":"t3"}}).values)

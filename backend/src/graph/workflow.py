'''
This module defines the DAG : Directed Acyclic Graph for the video audio processing pipeline.
It connects the nodes using the StateGraph from LangGraph.

START -> index_video_node -> audio_content_node -> END
'''

from langgraph.graph import StateGraph, START, END
from backend.src.graph.state import VideoAudioState

from backend.src.graph.nodes import index_video_node, audio_content_node

def create_graph():
    '''
    Constructs and compiles the graph workflow.
    Returns :
    Compiled Graph: runnable graph object for execution
    '''
    # initialize the graph with state schema
    workflow = StateGraph(VideoAudioState)
    workflow.add_node("indexer_node", index_video_node)
    workflow.add_node("auditor_node", audio_content_node)
    # def the entry point (where we want our graph to start)
    workflow.set_entry_point("indexer_node")
    # def the edges (connections between the 2 nodes)
    workflow.add_edge("indexer_node", "auditor_node")
    # once the auditor node is completed, we want to set the final status and report
    workflow.add_edge("auditor_node", END)
    # compile the graph
    return workflow.compile()

# expose this runnable app
app = create_graph()

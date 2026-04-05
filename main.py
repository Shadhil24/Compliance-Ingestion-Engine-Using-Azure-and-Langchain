'''
Main file for the multimodel-compliance-ingestion-engine
'''
import uuid
import json
import os
import sys
import logging
from pprint import pprint
from dotenv import load_dotenv
load_dotenv(override=True)

from backend.src.graph.workflow import app 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_cli_simulation():
    '''
    Run the CLI simulation
    '''
    # generate the session ID
    session_id = str(uuid.uuid4())
    logger.info(f"Starting the Audio Session: {session_id}")

    # define the initial state
    initial_inputs = {
        "video_url" : "https://www.youtube.com/watch?v=aP2up9N6H-g",
        "video_id" : f"vid_{session_id[:8]}",
        "compliance_results" : [],
        "errors" : []
    }

    print("\n--------Initializing the Workflow--------\n")
    print(f"Input Payload: {initial_inputs}")

    try:
        final_state = app.invoke(initial_inputs)
        print("\n--------Workflow Completed--------\n")
        print(f"\n Compliance Audit Report")
        print("-" * 50)
        print(f"Video ID: {final_state.get('video_id', 'N/A')}")
        print(f"Video URL: {final_state.get('video_url', 'N/A')}")
        print(f"Total Compliance Checks: {len(final_state.get('compliance_results', []))}")
        print(f"Total Errors: {len(final_state.get('errors', []))}")
        print("-" * 50)
        results = final_state.get('compliance_results', [])
        if results:
            for result in final_state.get('compliance_results', []):
                print(f"- [{result.get('severity').upper()}] {result.get('category')}: {result.get('description', 'N/A')}")
        else:
            print("No compliance results found")
        print("\n[FINAL SUMMARY]")
        print(final_state.get('final_report', 'N/A'))

    except Exception as e:
        logger.error(f"Error running the CLI simulation: {e}")
        raise e
        
if __name__ == "__main__":
    run_cli_simulation()
        
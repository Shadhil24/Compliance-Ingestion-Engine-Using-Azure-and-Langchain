import json
import os
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, SystemMessage

from backend.src.graph.state import VideoAudioState, ComplianceIssue

# IMPORT SERVICE
from backend.src.services.video_indexer import VideoIndexerService

logger = logging.getLogger("brand-guardian")
logging.basicConfig(level=logging.INFO)

# Node 1 : Video Indexer
# function for converting video to text
def index_video_node(state: VideoAudioState) -> Dict[str, Any]:
    '''
    Download the youtube video from the url
    Uploads to the Azure Video Indexer service
    extracts metadata and stores in the graph state
    '''
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo")

    logger.info(f"Indexing video: {video_url} with ID: {video_id_input}")

    local_file_name = f"temp_{video_id_input}.mp4"

    try:
        vi_service = VideoIndexerService()
        # download the video from the url
        if "youtube.com" in video_url or "youtu.be" in video_url:
            local_path = vi_service.download_youtube_video(video_url, local_file_name)
        else:
            raise Exception(f"Unsupported video URL: {video_url}")
        
        # upload
        azure_video_id = vi_service.upload_video(local_path, video_name=local_file_name)
        logger.info(f"Video uploaded to Azure Video Indexer with ID: {azure_video_id}")

        #cleanup
        if os.path.exists(local_path):
            os.remove(local_path)
        # wait
        raw_insights = vi_service.wait_for_video_processing(azure_video_id)
        # extract
        clean_data = vi_service.extract_data(raw_insights)
        logger.info(f"Video insights extracted: {clean_data}")
        return clean_data
    except Exception as e:
        logger.error(f"Error indexing video: {e}")
        return {
            "error": str(e),
            "final_status": "failed",
            "transcript": "",
            "ocr_text": []
        }

# Node 2 : Compliance Auditor
def audio_content_node(state: VideoAudioState) -> Dict[str, Any]:
    '''
    Performs RAG to audit the content
    '''
    logger.info("Performing RAG to audit the content")
    transcript = state.get("transcript", "")
    if not transcript:
        logger.warning("No transcript found, skipping RAG. Skipping audit....")
        return {
            "final_status": "failed",
            "final_report": "No transcript found, skipping RAG. Skipping audit....",
            "compliance_result": []
        }
    
    # Chat and embeddings may live on different Azure OpenAI resources (different regions / quotas).
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    embedding_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    embedding_key = os.getenv("AZURE_OPENAI_API_KEY")
    chat_endpoint = os.getenv("AZURE_OPENAI_CHAT_ENDPOINT") or embedding_endpoint
    chat_key = os.getenv("AZURE_OPENAI_CHAT_API_KEY") or embedding_key

    llm = AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        openai_api_version=api_version,
        azure_endpoint=chat_endpoint,
        api_key=chat_key,
        temperature=0.0,
    )

    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        openai_api_version=api_version,
        azure_endpoint=embedding_endpoint,
        api_key=embedding_key,
    )

    vector_store = AzureSearch(
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        embedding_function=embeddings.embed_query
    )

    # RAG retrieval
    ocr_text = state.get("ocr_text", [])
    query_text = f"{transcript} {''.join(ocr_text)}"
    docs = vector_store.similarity_search(query_text, k=3)
    retrieval_rules = "\n".join([doc.page_content for doc in docs])

    system_prompt = f"""
    You are a compliance auditor.
    OFFICIAL REGULATORY RULES:
    {retrieval_rules}
    INSTRUCTIONS:
    - Audit the transcript and OCR text for compliance with the official regulatory rules.
    - If any compliance issues are found, return the issue in the following format:
    - If no compliance issues are found, return "No compliance issues found."
    - The output should be in JSON format.
    - The output should be in the following format:
    {{
        "compliance_results": [
            {{
                "category": "Claim Validation",
                "description": "Explain the violation",
                "severity": "CRITICAL"
            }}
        ],
        "status": "FAIL",
        "final_report": "Explain the compliance issues found in the transcript and OCR text."
    }}
    If no violations are found, set the status to "PASS" and the final report to "No compliance issues found." and compliance_results to an empty list.
    """
    user_message = f"""
    Transcript: {transcript}
    VIDEO_METADATA: {state.get("video_metadata", {})}
    ON-SCREEN TEXT: {ocr_text}
    """

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ])
        content = response.content
        if "```" in content:
            content = re.search(r"```(?:json)?(.?)```", content, re.DOTALL).group(1)
        audit_data = json.loads(content.strip())
        return {
            "compliance_results": audit_data.get("compliance_results", []),
            "final_status": audit_data.get("status", "FAIL"),
            "final_report": audit_data.get("final_report", "No compliance issues found.")
        }
    except Exception as e:
        logger.error(f"Error auditing audio content: {e}")
        logger.error(f"RAW LLM Response: {response.content if 'response' in locals() else 'No response'}")
        return {
            "error": str(e),
            "compliance_results": [],
            "final_status": "failed",
            "final_report": f"Error auditing audio content: {e}"
        }

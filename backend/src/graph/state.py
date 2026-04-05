import operator 
from typing import Annotated, List, Dict, Optional, Any, TypedDict

#ddefine the schema for a single compliance result

class ComplianceIssue(TypedDict):
    category: str #general category of the issue
    description: str #specific description of the issue
    severity: str #severity of the issue
    timestamp: Optional[str]

# define the global graph state
class VideoAudioState(TypedDict):
    '''
    Defines the state for the video audio processing graph.
    '''
    video_url: str
    video_id: str

    # ingestion and extraction data
    local_file_path: Optional[str]
    video_metadata: Dict[str, Any] # {"duration": 15 , "resolution" : "1080p"}
    transcript: Optional[str]
    ocr_text: List[str]

    # analysis output
    compliance_result : Annotated[List[ComplianceIssue], operator.add]

    # final deliverables
    final_status : str
    final_report : str

    # system observability
    #errors : API timeouts, storage errors, etc.
    # list of system level crashes
    errors : Annotated[List[str], operator.add]


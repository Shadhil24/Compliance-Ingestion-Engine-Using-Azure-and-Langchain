'''
Connector : python and Azure video indexer
'''

import os 
import time 
import logging 
import requests 
import yt_dlp
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from azure.identity import DefaultAzureCredential

logger = logging.getLogger("brand-guardian")

def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

class VideoIndexerService:
    def __init__(self):
        self.accound_id = os.getenv("AZURE_VI_ACCOUNT_ID")
        self.location = os.getenv("AZURE_VI_LOCATION")
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = os.getenv("AZURE_RESOURCE_GROUP")
        self.vi_name = os.getenv("AZURE_VI_NAME")
        self.credential = DefaultAzureCredential()
        self.session = _build_session()

    def get_access_token(self):
        '''
        Get the access token for the Azure video indexer
        '''
        try:
            token_object = self.credential.get_token("https://management.azure.com/.default")
            return token_object.token
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            raise
    def get_account_token(self,arm_access_token):
        '''
        Exchange the ARM access token for a video indexer access token
        '''
        url = (
            f"https://management.azure.com/subscriptions/{self.subscription_id}"
            f"/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.VideoIndexer/accounts/{self.vi_name}"
            f"/generateAccessToken?api-version=2024-01-01"
        )
        headers = {
            "Authorization": f"Bearer {arm_access_token}",
            "Content-Type": "application/json"
        }
        payload = {"permissionType": "Contributor", "scope": "Account"}
        response = self.session.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            logger.error(f"Error getting account token: {response.json()}")
            raise Exception(f"Error getting account token: {response.json()}")
        return response.json()["accessToken"]
        
    def download_youtube_video(self, video_url, local_path):
        '''
        Download a youtube video to the local path
        '''
        try:
            ydl_opts = {
                'outtmpl': local_path,
                'format': 'best',
                'quiet': False,
                'no_warnings': False,
                'extractor_args': {'youtube': {'player_client': ['android','web']}},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
                return local_path
        except Exception as e:
            logger.error(f"Error downloading youtube video: {e}")
            raise

    # Upload the video to Azure Video Indexer
    def upload_video(self, local_path, video_name):
        '''
        Upload a video to the Azure video indexer
        '''
        try:
            access_token = self.get_access_token()
            account_token = self.get_account_token(access_token)
            url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.accound_id}/Videos"
            params = {
                "accessToken": account_token,
                "fileName": video_name,
                "name": video_name,
                "privacy": "Private",
                "indexingPreset": "Default"
            }

            logger.info(f"Uploading video to Azure Video Indexer: {video_name}")

            with open(local_path, "rb") as f:
                files = {
                    "file": (video_name, f, "application/octet-stream")
                }
                response = self.session.post(url, params=params, files=files, timeout=300)
            if response.status_code != 200:
                logger.error(f"Error uploading video: {response.json()}")
                raise Exception(f"Error uploading video: {response.json()}")
            return response.json().get("id")
        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            raise

    # Wait for the video to be processed
    def wait_for_video_processing(self, video_id):
        max_wait = int(os.getenv("AZURE_VI_MAX_WAIT_SECONDS", "3600"))
        poll_interval = int(os.getenv("AZURE_VI_POLL_INTERVAL_SECONDS", "30"))
        vi_token_ttl = int(os.getenv("AZURE_VI_TOKEN_REFRESH_SECONDS", "900"))
        logger.info(
            f"Waiting for video processing: {video_id} (max {max_wait}s, poll every {poll_interval}s)"
        )
        start = time.time()
        vi_access_token = None
        vi_token_obtained_at = 0.0

        def _fresh_vi_token():
            nonlocal vi_access_token, vi_token_obtained_at
            arm = self.get_access_token()
            vi_access_token = self.get_account_token(arm)
            vi_token_obtained_at = time.time()

        while True:
            elapsed = int(time.time() - start)
            if elapsed >= max_wait:
                raise TimeoutError(
                    f"Video {video_id} still not finished after {max_wait}s. "
                    f"Check status in Azure Video Indexer portal or increase AZURE_VI_MAX_WAIT_SECONDS."
                )
            try:
                if (
                    vi_access_token is None
                    or (time.time() - vi_token_obtained_at) >= vi_token_ttl
                ):
                    _fresh_vi_token()
                url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.accound_id}/Videos/{video_id}/Index"
                params = {"accessToken": vi_access_token}
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 401:
                    logger.warning("Video Indexer access token expired; refreshing")
                    _fresh_vi_token()
                    continue
                if not response.ok:
                    logger.error(
                        f"Video Indexer GET Index failed: {response.status_code} {response.text[:500]}"
                    )
                    raise Exception(
                        f"Video Indexer polling failed: HTTP {response.status_code}"
                    )
                data = response.json()
                state = data.get("state")
                if not state:
                    logger.error(f"Unexpected response from Video Indexer: {data}")
                    raise Exception(f"Unexpected response: {data}")
                if state == "Processed":
                    logger.info(f"Video processing finished after {elapsed}s")
                    return data
                elif state == "Failed":
                    logger.error(f"Video processing failed: {data}")
                    raise Exception(f"Video processing failed: {data}")
                elif state == "Quarantined":
                    raise Exception(
                        "Video processing quarantined (Copyright/ Content Policy Violation)"
                    )
                logger.info(
                    f"Video processing status: {state} (elapsed {elapsed}s / max {max_wait}s); "
                    f"next poll in {poll_interval}s"
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warning(f"Transient network error while polling, retrying: {e}")
            time.sleep(poll_interval)
    def extract_data(self, vi_json):
        transcript_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", []).get("transcript", []):
                transcript_lines.append(insight.get("text"))
        ocr_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", []).get("ocr", []):
                ocr_lines.append(insight.get("text"))
        return {
            "transcript": " ".join(transcript_lines),
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration": vi_json.get("summarizedInsights", {}).get("duration"),
                "platform" : "youtube"
            }
        }

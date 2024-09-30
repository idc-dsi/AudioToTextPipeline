# video_indexer.py

from dataclasses import dataclass
import requests

@dataclass
class VideoIndexer:
    subscription_key: str
    account_id: str
    location: str = "trial"

    def get_access_token(self):
        url =  f"https://api.videoindexer.ai/Auth/{self.location}/Accounts/{self.account_id}/AccessToken?allowEdit=true"
        headers = {"Ocp-Apim-Subscription-Key": self.subscription_key}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text.strip('"')

    def upload_video_and_get_indexed(self, video_file):
        access_token = self.get_access_token()
        params = {
            'accessToken': access_token,
            'name': video_file.filename,
            'privacy': 'Private',
            'description': 'Uploaded for indexing',
            'partition': 'none',
            'language': 'ar-IL'  # Set the video source language to Arabic (Israel)
        }
        files = {'file': (video_file.filename, video_file, 'video/mp4')}
        upload_url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos"
        response = requests.post(upload_url, params=params, files=files)
        response.raise_for_status()
        return response.json()['id']

    def get_video_index(self, video_id):
        access_token = self.get_access_token()
        url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos/{video_id}/Index?accessToken={access_token}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def get_video_captions(self, video_id):
        access_token = self.get_access_token()
        url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos/{video_id}/Captions"
        params = {
            'accessToken': access_token,
            'format': 'TXT',
            'includeSpeakerId': 'true',  # Include the speaker ID in the captions
            'language': 'ar-IL',
            
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.content.decode('utf-8')  # Ensure UTF-8 decoding
    
    def list_videos(self):
        access_token = self.get_access_token()
        url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos"
        params = {'accessToken': access_token}
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()['results']  # Adjust depending on actual response structure
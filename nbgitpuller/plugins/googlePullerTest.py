import os.path

import unittest

from google_auth_oauthlib.flow import InstalledAppFlow

from nbgitpuller.plugins.Folder.nbgitpuller.plugins import googlePuller
from googleapiclient.discovery import build
import pickle
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import asyncio

SCOPES = ['https://www.googleapis.com/auth/drive']


def auth():
    """Authenticates user to access Drive files."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)  # credentials.json download from drive API
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


class pullerTest(unittest.TestCase):
    def test_fetch(self):
        creds = auth()
        service = build('drive', 'v3', credentials=creds)
        obj = googlePuller.GooglePuller('https://docs.google.com/document/d/1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ/edit',
                                                 'xyz', 'yyyx', '1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ', 'student_name',
                                                 service)
        obj.fetch()
        assert os.path.exists('test.txt')
        os.remove('token.pickle')

    def test_checkIfRepoExists(self):
        creds = auth()
        service = build('drive', 'v3', credentials=creds)
        obj = googlePuller.GooglePuller(
            'https://docs.google.com/document/d/1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ/edit',
            'branch_name', '.', '1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ', 'student_name',
            service)
        obj.checkIfRepoExists()
        assert os.path.exists('.')
        os.remove('token.pickle')

    def test_pullNoRepo(self):
        creds = auth()
        service = build('drive', 'v3', credentials=creds)
        obj = googlePuller.GooglePuller(
            'https://docs.google.com/document/d/1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ/edit',
            'branch_name', '.', '1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ', 'student_name',
            service)
        obj.pull()
        assert os.path.exists('.')
        os.remove('token.pickle')

    def test_pullWithRepo(self):
        creds = auth()
        service = build('drive', 'v3', credentials=creds)
        obj = googlePuller.GooglePuller(
            'https://docs.google.com/document/d/1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ/edit',
            'branch_name', '.', '1PQjArHjcV8_T5c6YDnApOXivRTL-lxeIzfKn4-ly6lQ', 'student_name',
            service)
        obj.createRepo()
        obj.pull()


async def main():
    a = pullerTest()
    a.test_checkIfRepoExists()


asyncio.run(main())

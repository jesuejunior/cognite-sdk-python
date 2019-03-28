import os
import re

import pytest

from cognite.client import CogniteClient
from cognite.client.api.files import File, FileFilter, FileList, FileUpdate
from tests.utils import jsgz_load

FILES_API = CogniteClient().files


@pytest.fixture
def mock_files_response(rsps):
    response_body = {
        "data": {
            "items": [
                {
                    "externalId": "string",
                    "name": "string",
                    "source": "string",
                    "mimeType": "string",
                    "metadata": {},
                    "assetIds": [1],
                    "id": 1,
                    "uploaded": True,
                    "uploadedAt": 0,
                    "createdTime": 0,
                    "lastUpdatedTime": 0,
                }
            ]
        }
    }

    url_pattern = re.compile(re.escape(FILES_API._base_url) + "/.+")
    rsps.assert_all_requests_are_fired = False

    rsps.add(rsps.POST, url_pattern, status=200, json=response_body)
    rsps.add(rsps.GET, url_pattern, status=200, json=response_body)
    yield rsps


@pytest.fixture
def mock_file_upload_response(rsps):
    response_body = {
        "data": {
            "externalId": "string",
            "name": "string",
            "source": "string",
            "mimeType": "string",
            "metadata": {},
            "assetIds": [1],
            "id": 1,
            "uploaded": True,
            "uploadedAt": 0,
            "createdTime": 0,
            "lastUpdatedTime": 0,
            "uploadUrl": "https://upload.here",
        }
    }
    rsps.add(rsps.POST, FILES_API._base_url + "/files/initupload", status=200, json=response_body)
    rsps.add(rsps.PUT, "https://upload.here", status=200)
    yield rsps


@pytest.fixture
def mock_file_download_response(rsps):
    response_body = {
        "data": {
            "items": [
                {"id": 1, "link": "https://download.file1.here"},
                {"id": 2, "link": "https://download.file2.here"},
            ]
        }
    }
    rsps.add(rsps.POST, FILES_API._base_url + "/files/download", status=200, json=response_body)
    rsps.add(rsps.GET, "https://download.file1.here", status=200, body="content1")
    rsps.add(rsps.GET, "https://download.file2.here", status=200, body="content2")
    yield rsps
    for file_name in ["1", "2"]:
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        if os.path.isfile(file_path):
            os.remove(file_path)


class TestFilesAPI:
    def test_get_single(self, mock_files_response):
        res = FILES_API.get(id=1)
        assert isinstance(res, File)
        assert mock_files_response.calls[0].response.json()["data"]["items"][0] == res.dump(camel_case=True)

    def test_get_multiple(self, mock_files_response):
        res = FILES_API.get(id=[1])
        assert isinstance(res, FileList)
        assert mock_files_response.calls[0].response.json()["data"]["items"] == res.dump(camel_case=True)

    def test_list(self, mock_files_response):
        res = FILES_API.list(filter=FileFilter(source="bla"), limit=10)
        assert isinstance(res, FileList)
        assert mock_files_response.calls[0].response.json()["data"]["items"] == res.dump(camel_case=True)
        assert "bla" == jsgz_load(mock_files_response.calls[0].request.body)["filter"]["source"]
        assert 10 == jsgz_load(mock_files_response.calls[0].request.body)["limit"]

    def test_delete_single(self, mock_files_response):
        res = FILES_API.delete(id=1)
        assert {"items": [{"id": 1}]} == jsgz_load(mock_files_response.calls[0].request.body)
        assert res is None

    def test_delete_multiple(self, mock_files_response):
        res = FILES_API.delete(id=[1])
        assert {"items": [{"id": 1}]} == jsgz_load(mock_files_response.calls[0].request.body)
        assert res is None

    def test_update_with_resource_class(self, mock_files_response):
        res = FILES_API.update(File(id=1, name="bla"))
        assert isinstance(res, File)
        assert {"items": [{"id": 1, "update": {"name": {"set": "bla"}}}]} == jsgz_load(
            mock_files_response.calls[0].request.body
        )

    def test_update_with_update_class(self, mock_files_response):
        res = FILES_API.update(FileUpdate(id=1).name_set("bla"))
        assert isinstance(res, File)
        assert {"items": [{"id": 1, "update": {"name": {"set": "bla"}}}]} == jsgz_load(
            mock_files_response.calls[0].request.body
        )

    def test_update_multiple(self, mock_files_response):
        res = FILES_API.update([FileUpdate(id=1).name_set(None), File(external_id="2", name="bla")])
        assert isinstance(res, FileList)
        assert {
            "items": [
                {"id": 1, "update": {"name": {"setNull": True}}},
                {"externalId": "2", "update": {"name": {"set": "bla"}}},
            ]
        } == jsgz_load(mock_files_response.calls[0].request.body)

    def test_iter_single(self, mock_files_response):
        for file in FILES_API:
            assert isinstance(file, File)
            assert mock_files_response.calls[0].response.json()["data"]["items"][0] == file.dump(camel_case=True)

    def test_iter_chunk(self, mock_files_response):
        for file in FILES_API(chunk_size=1):
            assert isinstance(file, FileList)
            assert mock_files_response.calls[0].response.json()["data"]["items"] == file.dump(camel_case=True)

    def test_upload(self, mock_file_upload_response):
        path = os.path.join(os.path.dirname(__file__), "file_for_test_upload.txt")
        res = FILES_API.upload(File(name="bla"), path=path)
        response_body = mock_file_upload_response.calls[0].response.json()["data"]
        del response_body["uploadUrl"]
        assert File._load(response_body) == res
        assert "https://upload.here/" == mock_file_upload_response.calls[1].request.url
        assert b"content\n" == mock_file_upload_response.calls[1].request.body

    def test_upload_from_memory(self, mock_file_upload_response):
        res = FILES_API.upload_from_memory(File(name="bla"), content=b"content")
        response_body = mock_file_upload_response.calls[0].response.json()["data"]
        del response_body["uploadUrl"]
        assert File._load(response_body) == res
        assert "https://upload.here/" == mock_file_upload_response.calls[1].request.url
        assert b"content" == mock_file_upload_response.calls[1].request.body

    def test_download(self, mock_file_download_response):
        curdir = os.path.dirname(__file__)
        res = FILES_API.download(directory=curdir, id=[1, 2])
        assert res is None
        assert os.path.isfile(os.path.join(curdir, "1"))
        assert os.path.isfile(os.path.join(curdir, "2"))

    def test_download_to_memory(self, mock_file_download_response):
        mock_file_download_response.assert_all_requests_are_fired = False
        res = FILES_API.download_to_memory(id=1)
        assert res == b"content1"

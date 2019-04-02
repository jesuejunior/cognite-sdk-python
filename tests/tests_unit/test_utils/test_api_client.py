# -*- coding: utf-8 -*-
import gzip
import json
from collections import namedtuple

import pytest

from cognite.client import APIError
from cognite.client._utils.api_client import APIClient
from cognite.client._utils.resource_base import CogniteResource, CogniteResourceList, CogniteUpdate
from tests.utils import jsgz_load

BASE_URL = "http://localtest.com/api/1.0/projects/test_proj"
URL_PATH = "/someurl"

RESPONSE = {"any": "ok"}

API_CLIENT = APIClient(
    project="test_proj", base_url=BASE_URL, max_workers=1, cookies={"a-cookie": "a-cookie-val"}, headers={}, timeout=60
)


class TestBasicRequests:
    @pytest.fixture
    def mock_all_requests_ok(self, rsps):
        rsps.assert_all_requests_are_fired = False
        for method in [rsps.GET, rsps.PUT, rsps.POST, rsps.DELETE]:
            rsps.add(method, BASE_URL + URL_PATH, status=200, json=RESPONSE)

    @pytest.fixture
    def mock_all_requests_fail(self, rsps):
        rsps.assert_all_requests_are_fired = False
        for method in [rsps.GET, rsps.PUT, rsps.POST, rsps.DELETE]:
            rsps.add(method, BASE_URL + URL_PATH, status=400, json={"error": "Client error"})
            rsps.add(method, BASE_URL + URL_PATH, status=500, body="Server error")
            rsps.add(method, BASE_URL + URL_PATH, status=500, json={"error": "Server error"})
            rsps.add(method, BASE_URL + URL_PATH, status=400, json={"error": {"code": 400, "message": "Client error"}})

    RequestCase = namedtuple("RequestCase", ["name", "method", "kwargs"])

    request_cases = [
        RequestCase(name="post", method=API_CLIENT._post, kwargs={"url_path": URL_PATH, "json": {"any": "ok"}}),
        RequestCase(name="get", method=API_CLIENT._get, kwargs={"url_path": URL_PATH}),
        RequestCase(name="delete", method=API_CLIENT._delete, kwargs={"url_path": URL_PATH}),
        RequestCase(name="put", method=API_CLIENT._put, kwargs={"url_path": URL_PATH, "json": {"any": "ok"}}),
    ]

    @pytest.mark.usefixtures("mock_all_requests_ok")
    @pytest.mark.parametrize("name, method, kwargs", request_cases)
    def test_requests_ok(self, name, method, kwargs):
        response = method(**kwargs)
        assert response.status_code == 200
        assert response.json() == RESPONSE

    @pytest.mark.usefixtures("mock_all_requests_fail")
    @pytest.mark.parametrize("name, method, kwargs", request_cases)
    def test_requests_fail(self, name, method, kwargs):
        with pytest.raises(APIError, match="Client error") as e:
            method(**kwargs)
        assert e.value.code == 400

        with pytest.raises(APIError, match="Server error") as e:
            method(**kwargs)
        assert e.value.code == 500

        with pytest.raises(APIError, match="Server error") as e:
            method(**kwargs)
        assert e.value.code == 500

        with pytest.raises(APIError, match="Client error | code: 400 | X-Request-ID:") as e:
            method(**kwargs)
        assert e.value.code == 400
        assert e.value.message == "Client error"

    @pytest.mark.usefixtures("disable_gzip")
    def test_request_gzip_disabled(self, rsps):
        def check_gzip_disabled(request):
            assert "Content-Encoding" not in request.headers
            assert {"any": "OK"} == json.loads(request.body)
            return 200, {}, json.dumps(RESPONSE)

        for method in [rsps.PUT, rsps.POST]:
            rsps.add_callback(method, BASE_URL + URL_PATH, check_gzip_disabled)

        API_CLIENT._post(URL_PATH, {"any": "OK"}, headers={})
        API_CLIENT._put(URL_PATH, {"any": "OK"}, headers={})

    def test_request_gzip_enabled(self, rsps):
        def check_gzip_enabled(request):
            assert "Content-Encoding" in request.headers
            assert {"any": "OK"} == jsgz_load(request.body)
            return 200, {}, json.dumps(RESPONSE)

        for method in [rsps.PUT, rsps.POST]:
            rsps.add_callback(method, BASE_URL + URL_PATH, check_gzip_enabled)

        API_CLIENT._post(URL_PATH, {"any": "OK"}, headers={})
        API_CLIENT._put(URL_PATH, {"any": "OK"}, headers={})


class SomeResource(CogniteResource):
    def __init__(self, x=None, y=None, id=None, external_id=None):
        self.x = x
        self.y = y
        self.id = id
        self.external_id = external_id


class SomeResourceList(CogniteResourceList):
    _RESOURCE = SomeResource


class TestStandardRetrieve:
    def test_standard_retrieve_OK(self, rsps):
        rsps.add(
            rsps.GET, BASE_URL + URL_PATH + "/1", status=200, json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}}
        )

        assert SomeResource(1, 2) == API_CLIENT._retrieve(cls=SomeResource, resource_path=URL_PATH, id=1)

    def test_standard_retrieve_fail(self, rsps):
        rsps.add(rsps.GET, BASE_URL + URL_PATH + "/1", status=400, json={"error": {"message": "Client Error"}})
        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._retrieve(cls=SomeResource, resource_path=URL_PATH, id=1)
        assert "Client Error" == e.value.message
        assert 400 == e.value.code


class TestStandardRetrieveById:
    @pytest.fixture
    def mock_by_ids(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/byids",
            status=200,
            json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}},
        )
        yield rsps

    def test_by_id_no_wrap_OK(self, mock_by_ids):
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=False, ids=[1, 2]
        )
        assert {"items": [1, 2]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_single_id_no_wrap_OK(self, mock_by_ids):
        assert SomeResource(1, 2) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=False, ids=1
        )
        assert {"items": [1]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_id_wrap_OK(self, mock_by_ids):
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, ids=[1, 2]
        )
        assert {"items": [{"id": 1}, {"id": 2}]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_single_id_wrap_OK(self, mock_by_ids):
        assert SomeResource(1, 2) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, ids=1
        )
        assert {"items": [{"id": 1}]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_external_id_wrap_OK(self, mock_by_ids):
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, external_ids=["1", "2"]
        )
        assert {"items": [{"externalId": "1"}, {"externalId": "2"}]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_single_external_id_wrap_OK(self, mock_by_ids):
        assert SomeResource(1, 2) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, external_ids="1"
        )
        assert {"items": [{"externalId": "1"}]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_by_external_id_no_wrap(self):
        with pytest.raises(ValueError, match="must be wrapped"):
            API_CLIENT._retrieve_multiple(
                cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=False, external_ids=["1", "2"]
            )

    def test_id_and_external_id_mixed(self, mock_by_ids):
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._retrieve_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, ids=1, external_ids=["2"]
        )
        assert {"items": [{"id": 1}, {"externalId": "2"}]} == jsgz_load(mock_by_ids.calls[0].request.body)

    def test_standard_retrieve_multiple_fail(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/byids", status=400, json={"error": {"message": "Client Error"}})
        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._retrieve_multiple(cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=True, ids=[1, 2])
        assert "Client Error" == e.value.message
        assert 400 == e.value.code

    def test_ids_all_None(self):
        with pytest.raises(ValueError, match="No ids specified"):
            API_CLIENT._retrieve_multiple(cls=SomeResourceList, resource_path=URL_PATH, wrap_ids=False)


class TestStandardList:
    def test_standard_list_ok(self, rsps):
        rsps.add(rsps.GET, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}})
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._list(
            cls=SomeResourceList, resource_path=URL_PATH, method="GET"
        )

    def test_standard_list_with_filter_GET_ok(self, rsps):
        rsps.add(rsps.GET, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}})
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._list(
            cls=SomeResourceList, resource_path=URL_PATH, method="GET", filter={"filter": "bla"}
        )
        assert "filter=bla" in rsps.calls[0].request.path_url

    def test_standard_list_with_filter_POST_ok(self, rsps):
        rsps.add(
            rsps.POST, BASE_URL + URL_PATH + "/list", status=200, json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}}
        )
        assert SomeResourceList([SomeResource(1, 2), SomeResource(1)]) == API_CLIENT._list(
            cls=SomeResourceList, resource_path=URL_PATH, method="POST", filter={"filter": "bla"}
        )
        assert {"filter": {"filter": "bla"}, "limit": 1000, "cursor": None} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_list_fail(self, rsps):
        rsps.add(rsps.GET, BASE_URL + URL_PATH, status=400, json={"error": {"message": "Client Error"}})
        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._list(cls=SomeResourceList, resource_path=URL_PATH, method="GET")
        assert 400 == e.value.code
        assert "Client Error" == e.value.message

    NUMBER_OF_ITEMS_FOR_AUTOPAGING = 11500
    ITEMS_TO_GET_WHILE_AUTOPAGING = [{"x": 1, "y": 1} for _ in range(NUMBER_OF_ITEMS_FOR_AUTOPAGING)]

    @pytest.fixture
    def mock_get_for_autopaging(self, rsps):
        def callback(request):
            params = {elem.split("=")[0]: elem.split("=")[1] for elem in request.path_url.split("?")[-1].split("&")}
            limit = int(params["limit"])
            cursor = int(params.get("cursor") or 0)
            items = self.ITEMS_TO_GET_WHILE_AUTOPAGING[cursor : cursor + limit]
            if cursor + limit >= self.NUMBER_OF_ITEMS_FOR_AUTOPAGING:
                next_cursor = None
            else:
                next_cursor = cursor + limit
            response = json.dumps({"data": {"nextCursor": next_cursor, "items": items}})
            return 200, {}, response

        rsps.add_callback(rsps.GET, BASE_URL + URL_PATH, callback)

    @pytest.mark.usefixtures("mock_get_for_autopaging")
    def test_standard_list_generator(self):
        total_resources = 0
        for resource in API_CLIENT._list_generator(
            cls=SomeResourceList, resource_path=URL_PATH, method="GET", limit=10000
        ):
            assert isinstance(resource, SomeResource)
            total_resources += 1
        assert 10000 == total_resources

    @pytest.mark.usefixtures("mock_get_for_autopaging")
    def test_standard_list_generator(self):
        total_resources = 0
        for resource_chunk in API_CLIENT._list_generator(
            cls=SomeResourceList, resource_path=URL_PATH, method="GET", limit=10000, chunk=1000
        ):
            assert isinstance(resource_chunk, SomeResourceList)
            assert 1000 == len(resource_chunk)
            total_resources += 1000
        assert 10000 == total_resources

    def test_standard_list_generator__chunk_size_exceeds_max(self):
        with pytest.raises(AssertionError, match="exceed 1000"):
            for _ in API_CLIENT._list_generator(cls=SomeResourceList, resource_path=URL_PATH, method="GET", chunk=1001):
                pass

    @pytest.mark.usefixtures("mock_get_for_autopaging")
    def test_standard_list_autopaging(self):
        res = API_CLIENT._list(cls=SomeResourceList, resource_path=URL_PATH, method="GET")
        assert self.NUMBER_OF_ITEMS_FOR_AUTOPAGING == len(res)

    @pytest.mark.usefixtures("mock_get_for_autopaging")
    def test_standard_list_autopaging_with_limit(self):
        res = API_CLIENT._list(cls=SomeResourceList, resource_path=URL_PATH, method="GET", limit=5333)
        assert 5333 == len(res)


class TestStandardCreate:
    def test_standard_create_ok(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}, {"x": 1}]}})
        res = API_CLIENT._create_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, items=[SomeResource(1, 1), SomeResource(1)]
        )
        assert {"items": [{"x": 1, "y": 1}, {"x": 1}]} == jsgz_load(rsps.calls[0].request.body)
        assert SomeResource(1, 2) == res[0]
        assert SomeResource(1) == res[1]

    def test_standard_create_single_item_ok(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}]}})
        res = API_CLIENT._create_multiple(cls=SomeResourceList, resource_path=URL_PATH, items=SomeResource(1, 2))
        assert {"items": [{"x": 1, "y": 2}]} == jsgz_load(rsps.calls[0].request.body)
        assert SomeResource(1, 2) == res

    def test_standard_create_single_item_in_list_ok(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}]}})
        res = API_CLIENT._create_multiple(cls=SomeResourceList, resource_path=URL_PATH, items=[SomeResource(1, 2)])
        assert {"items": [{"x": 1, "y": 2}]} == jsgz_load(rsps.calls[0].request.body)
        assert SomeResourceList([SomeResource(1, 2)]) == res

    def test_standard_create_fail(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=400, json={"error": {"message": "Client Error"}})
        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._create_multiple(
                cls=SomeResourceList, resource_path=URL_PATH, items=[SomeResource(1, 1), SomeResource(1)]
            )
        assert 400 == e.value.code
        assert "Client Error" == e.value.message

    def test_standard_create_concurrent(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 1, "y": 2}]}})
        rsps.add(rsps.POST, BASE_URL + URL_PATH, status=200, json={"data": {"items": [{"x": 3, "y": 4}]}})

        res = API_CLIENT._create_multiple(
            cls=SomeResourceList, resource_path=URL_PATH, items=[SomeResource(1, 2), SomeResource(3, 4)], limit=1
        )
        assert SomeResourceList([SomeResource(1, 2), SomeResource(3, 4)]) == res

        assert {"items": [{"x": 1, "y": 2}]} == jsgz_load(rsps.calls[0].request.body)
        assert {"items": [{"x": 3, "y": 4}]} == jsgz_load(rsps.calls[1].request.body)


class TestStandardDelete:
    def test_standard_delete_multiple_ok(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/delete", status=200, json={})
        API_CLIENT._delete_multiple(resource_path=URL_PATH, wrap_ids=False, ids=[1, 2])
        assert {"items": [1, 2]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_delete_multiple_ok__single_id(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/delete", status=200, json={})
        API_CLIENT._delete_multiple(resource_path=URL_PATH, wrap_ids=False, ids=1)
        assert {"items": [1]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_delete_multiple_ok__single_id_in_list(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/delete", status=200, json={})
        API_CLIENT._delete_multiple(resource_path=URL_PATH, wrap_ids=False, ids=[1])
        assert {"items": [1]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_delete_multiple_fail(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/delete", status=400, json={"error": {"message": "Client Error"}})
        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._delete_multiple(resource_path=URL_PATH, wrap_ids=False, ids=[1, 2])
        assert 400 == e.value.code
        assert "Client Error" == e.value.message


class SomeUpdate(CogniteUpdate):
    def __init__(self, id=None, external_id=None):
        self.id = id
        self.external_id = external_id
        self._update_object = {}

    def y_set(self, value: int):
        if value is None:
            self._update_object["y"] = {"setNull": True}
            return self
        self._update_object["y"] = {"set": value}
        return self


class TestStandardUpdate:
    def test_standard_update_with_cognite_resource_OK(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/update",
            status=200,
            json={"data": {"items": [{"id": 1, "x": 1, "y": 100}]}},
        )
        res = API_CLIENT._update_multiple(SomeResourceList, resource_path=URL_PATH, items=[SomeResource(id=1, y=100)])
        assert SomeResourceList([SomeResource(id=1, x=1, y=100)]) == res
        assert {"items": [{"id": 1, "update": {"y": {"set": 100}}}]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_update_with_cognite_resource_and_external_id_OK(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/update",
            status=200,
            json={"data": {"items": [{"id": 1, "x": 1, "y": 100}]}},
        )
        res = API_CLIENT._update_multiple(
            SomeResourceList, resource_path=URL_PATH, items=[SomeResource(external_id="1", y=100)]
        )
        assert SomeResourceList([SomeResource(id=1, x=1, y=100)]) == res
        assert {"items": [{"externalId": "1", "update": {"y": {"set": 100}}}]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_update_with_cognite_resource__id_error(self):
        with pytest.raises(AssertionError, match="one of 'id' and 'external_id'"):
            API_CLIENT._update_multiple(SomeResourceList, resource_path=URL_PATH, items=[SomeResource(y=100)])

        with pytest.raises(AssertionError, match="one of 'id' and 'external_id'"):
            API_CLIENT._update_multiple(
                SomeResourceList, resource_path=URL_PATH, items=[SomeResource(id=1, external_id=1, y=100)]
            )

    def test_standard_update_with_cognite_update_object_OK(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/update",
            status=200,
            json={"data": {"items": [{"id": 1, "x": 1, "y": 100}]}},
        )
        res = API_CLIENT._update_multiple(SomeResourceList, resource_path=URL_PATH, items=[SomeUpdate(id=1).y_set(100)])
        assert SomeResourceList([SomeResource(id=1, x=1, y=100)]) == res
        assert {"items": [{"id": 1, "update": {"y": {"set": 100}}}]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_update_single_object(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/update",
            status=200,
            json={"data": {"items": [{"id": 1, "x": 1, "y": 100}]}},
        )
        res = API_CLIENT._update_multiple(SomeResourceList, resource_path=URL_PATH, items=SomeUpdate(id=1).y_set(100))
        assert SomeResource(id=1, x=1, y=100) == res
        assert {"items": [{"id": 1, "update": {"y": {"set": 100}}}]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_update_with_cognite_update_object_and_external_id_OK(self, rsps):
        rsps.add(
            rsps.POST,
            BASE_URL + URL_PATH + "/update",
            status=200,
            json={"data": {"items": [{"id": 1, "x": 1, "y": 100}]}},
        )
        res = API_CLIENT._update_multiple(
            SomeResourceList, resource_path=URL_PATH, items=[SomeUpdate(external_id="1").y_set(100)]
        )
        assert SomeResourceList([SomeResource(id=1, x=1, y=100)]) == res
        assert {"items": [{"externalId": "1", "update": {"y": {"set": 100}}}]} == jsgz_load(rsps.calls[0].request.body)

    def test_standard_update_fail(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/update", status=400, json={"error": {"message": "Client Error"}})

        with pytest.raises(APIError, match="Client Error"):
            API_CLIENT._update_multiple(SomeResourceList, resource_path=URL_PATH, items=[])


class TestStandardSearch:
    def test_standard_search_ok(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/search", status=200, json={"data": {"items": [{"x": 1, "y": 2}]}})

        res = API_CLIENT._search(
            cls=SomeResourceList,
            resource_path=URL_PATH,
            json={"search": {"name": "bla"}, "limit": 1000, "filter": {"name": "bla"}},
        )
        assert SomeResourceList([SomeResource(1, 2)]) == res
        assert {"search": {"name": "bla"}, "limit": 1000, "filter": {"name": "bla"}} == jsgz_load(
            rsps.calls[0].request.body
        )

    def test_standard_search_fail(self, rsps):
        rsps.add(rsps.POST, BASE_URL + URL_PATH + "/search", status=400, json={"error": {"message": "Client Error"}})

        with pytest.raises(APIError, match="Client Error") as e:
            API_CLIENT._search(cls=SomeResourceList, resource_path=URL_PATH, json={})
        assert "Client Error" == e.value.message
        assert 400 == e.value.code


class TestMiscellaneous:
    @pytest.mark.parametrize(
        "input, expected",
        [
            (
                "https://api.cognitedata.com/api/0.6/projects/test-project/analytics/models",
                "http://localhost:8000/api/0.1/projects/test-project/models",
            ),
            (
                "https://api.cognitedata.com/api/0.6/projects/test-project/analytics/models/sourcepackages/1",
                "http://localhost:8000/api/0.1/projects/test-project/models/sourcepackages/1",
            ),
            (
                "https://api.cognitedata.com/api/0.6/projects/test-project/assets/update",
                "https://api.cognitedata.com/api/0.6/projects/test-project/assets/update",
            ),
        ],
    )
    def test_nostromo_emulator_url_converter(self, input, expected):
        assert expected == API_CLIENT._model_hosting_emulator_url_converter(input)

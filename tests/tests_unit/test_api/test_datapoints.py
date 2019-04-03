import json
from random import random

import pytest

from cognite.client import CogniteClient
from cognite.client._utils import utils
from cognite.client.api.datapoints import Datapoints, DatapointsList, DatapointsQuery, _DPWindow
from tests.utils import jsgz_load

DPS_CLIENT = CogniteClient(debug=True, max_workers=20).datapoints


def generate_datapoints(start: int, end: int, aggregates=None, granularity=None):
    dps = []
    granularity = utils.granularity_to_ms(granularity) if granularity else 1000
    for i in range(start, end, granularity):
        dp = {}
        if aggregates:
            for agg in aggregates:
                dp[agg] = random()
        else:
            dp["value"] = random()
        dp["timestamp"] = i
        dps.append(dp)
    return dps


@pytest.fixture
def mock_get_datapoints(rsps):
    def request_callback(request):
        payload = jsgz_load(request.body)

        items = []
        for dps_query in payload["items"]:
            aggregates = []

            if "aggregates" in dps_query:
                aggregates = dps_query["aggregates"]
            elif "aggregates" in payload:
                aggregates = payload["aggregates"]

            granularity = None
            if "granularity" in dps_query:
                granularity = dps_query["granularity"]
            elif "granularity" in payload:
                granularity = payload["granularity"]

            if (granularity and not aggregates) or (not granularity and aggregates):
                return (
                    400,
                    {},
                    json.dumps({"error": {"code": 400, "message": "You must specify both aggregates AND granularity"}}),
                )

            if "start" in dps_query and "end" in dps_query:
                start, end = dps_query["start"], dps_query["end"]
            else:
                start, end = payload["start"], payload["end"]

            limit = 100000
            if "limit" in dps_query:
                limit = dps_query["limit"]
            elif "limit" in payload:
                limit = payload["limit"]

            dps = generate_datapoints(start, end, aggregates, granularity)
            dps = dps[:limit]
            id_to_return = dps_query.get("id", -1)
            external_id_to_return = dps_query.get("externalId", "-1")
            items.append({"id": id_to_return, "externalId": external_id_to_return, "datapoints": dps})
        response = {"data": {"items": items}}
        return 200, {}, json.dumps(response)

    rsps.add_callback(
        rsps.POST,
        DPS_CLIENT._base_url + "/timeseries/data/get",
        callback=request_callback,
        content_type="application/json",
    )
    yield rsps


@pytest.fixture
def mock_get_datapoints_empty(rsps):
    rsps.add(
        rsps.POST,
        DPS_CLIENT._base_url + "/timeseries/data/get",
        status=200,
        json={"data": {"items": [{"id": 1, "externalId": "1", "datapoints": []}]}},
    )
    yield rsps


@pytest.fixture
def set_dps_limits():
    def set_limit(limit):
        DPS_CLIENT._LIMIT_AGG = limit
        DPS_CLIENT._LIMIT = limit

    limit_agg_tmp = DPS_CLIENT._LIMIT_AGG
    limit_tmp = DPS_CLIENT._LIMIT
    yield set_limit
    DPS_CLIENT._LIMIT_AGG = limit_agg_tmp
    DPS_CLIENT._LIMIT = limit_tmp


@pytest.fixture
def set_dps_workers():
    def set_limit(limit):
        DPS_CLIENT._max_workers = limit

    workers_tmp = DPS_CLIENT._max_workers
    yield set_limit
    DPS_CLIENT._max_workers = workers_tmp


def assert_dps_response_is_correct(calls, dps_object):
    datapoints = []
    for call in calls:
        dps_response = call.response.json()["data"]["items"][0]
        if dps_response["id"] == dps_object.id and dps_response["externalId"] == dps_object.external_id:
            datapoints.extend(dps_response["datapoints"])
            id = dps_response["id"]
            external_id = dps_response["externalId"]

    assert {
        "id": id,
        "externalId": external_id,
        "datapoints": sorted(datapoints, key=lambda x: x["timestamp"]),
    } == dps_object.dump(camel_case=True)


class TestGetDatapoints:
    def test_get_datapoints_by_id(self, mock_get_datapoints):
        dps_res = DPS_CLIENT.get(id=123, start=1000000, end=1100000)
        assert isinstance(dps_res, Datapoints)
        assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_get_datapoints_by_external_id(self, mock_get_datapoints):
        dps_res = DPS_CLIENT.get(external_id="123", start=1000000, end=1100000)
        assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_get_datapoints_aggregates(self, mock_get_datapoints):
        dps_res = DPS_CLIENT.get(
            id=123, start=1000000, end=1100000, aggregates=["average", "stepInterpolation"], granularity="10s"
        )
        assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_get_datapoints_local_aggregates(self, mock_get_datapoints):
        dps_res_list = DPS_CLIENT.get(
            external_id={"externalId": "123", "aggregates": ["average"]},
            id={"id": 123},
            start=1000000,
            end=1100000,
            aggregates=["max"],
            granularity="10s",
        )
        for dps_res in dps_res_list:
            assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_datapoints_paging(self, mock_get_datapoints, set_dps_limits, set_dps_workers):
        set_dps_workers(1)
        set_dps_limits(1)
        dps_res = DPS_CLIENT.get(id=123, start=0, end=10000, aggregates=["average"], granularity="1s")
        assert 10 == len(dps_res)

    def test_datapoints_concurrent(self, mock_get_datapoints, set_dps_workers, set_dps_limits):
        set_dps_workers(5)
        dps_res = DPS_CLIENT.get(id=123, start=0, end=20000, aggregates=["average"], granularity="1s")
        requested_windows = sorted(
            [
                (jsgz_load(call.request.body)["start"], jsgz_load(call.request.body)["end"])
                for call in mock_get_datapoints.calls
            ],
            key=lambda x: x[0],
        )

        assert [(0, 4000), (5000, 9000), (10000, 14000), (15000, 19000)] == requested_windows
        assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    @pytest.mark.parametrize(
        "max_workers, aggregates, granularity, actual_windows_req",
        [
            (1, None, None, [(0, 20000), (9001, 20000), (18002, 20000)]),
            (2, None, None, [(0, 10000), (9001, 10000), (10001, 20000), (19002, 20000)]),
            (3, None, None, [(0, 6666), (6667, 13333), (13334, 20000)]),
            (4, ["average"], "1s", [(0, 5000), (6000, 11000), (12000, 17000), (18000, 20000)]),
            (2, ["average"], "5s", [(0, 10000), (15000, 20000)]),
            (4, ["average"], "5s", [(0, 5000), (10000, 15000)]),
        ],
    )
    def test_request_dps_spacing_correct(
        self,
        mock_get_datapoints,
        set_dps_workers,
        set_dps_limits,
        max_workers,
        aggregates,
        granularity,
        actual_windows_req,
    ):
        set_dps_limits(10)
        set_dps_workers(max_workers)
        DPS_CLIENT.get(id=123, start=0, end=20000, aggregates=aggregates, granularity=granularity)
        requested_windows = sorted(
            [
                (jsgz_load(call.request.body)["start"], jsgz_load(call.request.body)["end"])
                for call in mock_get_datapoints.calls
            ],
            key=lambda x: x[0],
        )
        assert actual_windows_req == requested_windows

    def test_datapoints_paging_with_limit(self, mock_get_datapoints, set_dps_limits):
        set_dps_limits(3)
        dps_res = DPS_CLIENT.get(id=123, start=0, end=10000, aggregates=["average"], granularity="1s", limit=4)
        assert 4 == len(dps_res)

    def test_get_datapoints_multiple_time_series(self, mock_get_datapoints, set_dps_limits):
        set_dps_limits(10)
        ids = [1, 2, 3]
        external_ids = ["4", "5", "6"]
        dps_res_list = DPS_CLIENT.get(id=ids, external_id=external_ids, start=0, end=100000)
        assert isinstance(dps_res_list, DatapointsList)
        for dps_res in dps_res_list:
            if dps_res.id in ids:
                ids.remove(dps_res.id)
            if dps_res.external_id in external_ids:
                external_ids.remove(dps_res.external_id)
            assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)
        assert 0 == len(ids)
        assert 0 == len(external_ids)

    def test_get_datapoints_empty(self, mock_get_datapoints_empty):
        res = DPS_CLIENT.get(id=1, start=0, end=10000)
        assert 0 == len(res)


class TestQueryDatapoints:
    def test_query_single(self, mock_get_datapoints):
        dps_res = DPS_CLIENT.query(query=DatapointsQuery(id=1, start=0, end=10000))
        assert isinstance(dps_res, Datapoints)
        assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_query_multiple(self, mock_get_datapoints):
        dps_res_list = DPS_CLIENT.query(
            query=[
                DatapointsQuery(id=1, start=0, end=10000),
                DatapointsQuery(external_id="1", start=10000, end=20000, aggregates=["average"], granularity="2s"),
            ]
        )
        assert isinstance(dps_res_list, DatapointsList)
        for dps_res in dps_res_list:
            assert_dps_response_is_correct(mock_get_datapoints.calls, dps_res)

    def test_query_empty(self, mock_get_datapoints_empty):
        dps_res = DPS_CLIENT.query(query=DatapointsQuery(id=1, start=0, end=10000))
        assert 0 == len(dps_res)


@pytest.fixture
def mock_get_latest(rsps):
    def request_callback(request):
        payload = jsgz_load(request.body)

        items = []
        for latest_query in payload["items"]:
            id = latest_query.get("id", -1)
            external_id = latest_query.get("externalId", "-1")
            before = latest_query.get("before", 10001)
            items.append(
                {"id": id, "externalId": external_id, "datapoints": [{"timestamp": before - 1, "value": random()}]}
            )
        return 200, {}, json.dumps({"data": {"items": items}})

    rsps.add_callback(
        rsps.POST,
        DPS_CLIENT._base_url + "/timeseries/data/latest",
        callback=request_callback,
        content_type="application/json",
    )
    yield rsps


@pytest.fixture
def mock_get_latest_empty(rsps):
    rsps.add(
        rsps.POST,
        DPS_CLIENT._base_url + "/timeseries/data/latest",
        status=200,
        json={
            "data": {
                "items": [
                    {"id": 1, "externalId": "1", "datapoints": []},
                    {"id": 2, "externalId": "2", "datapoints": []},
                ]
            }
        },
    )
    yield rsps


class TestGetLatest:
    def test_get_latest(self, mock_get_latest):
        res = DPS_CLIENT.get_latest(id=1)
        assert isinstance(res, Datapoints)
        assert 10000 == res[0].timestamp
        assert isinstance(res[0].value, float)

    def test_get_latest_multiple_ts(self, mock_get_latest):
        res = DPS_CLIENT.get_latest(id=1, external_id="2")
        assert isinstance(res, DatapointsList)
        for dps in res:
            assert 10000 == dps[0].timestamp
            assert isinstance(dps[0].value, float)

    def test_get_latest_with_before(self, mock_get_latest):
        res = DPS_CLIENT.get_latest(id=1, before=10)
        assert isinstance(res, Datapoints)
        assert 9 == res[0].timestamp
        assert isinstance(res[0].value, float)

    def test_get_latest_multiple_ts_with_before(self, mock_get_latest):
        res = DPS_CLIENT.get_latest(id=[1, 2], external_id=["1", "2"], before=10)
        assert isinstance(res, DatapointsList)
        for dps in res:
            assert 9 == dps[0].timestamp
            assert isinstance(dps[0].value, float)

    def test_get_latest_empty(self, mock_get_latest_empty):
        res = DPS_CLIENT.get_latest(id=1)
        assert isinstance(res, Datapoints)
        assert 0 == len(res)

    def test_get_latest_multiple_ts_empty(self, mock_get_latest_empty):
        res_list = DPS_CLIENT.get_latest(id=[1, 2])
        assert isinstance(res_list, DatapointsList)
        assert 2 == len(res_list)
        for res in res_list:
            assert 0 == len(res)


@pytest.fixture
def mock_post_datapoints(rsps):
    rsps.add(rsps.POST, DPS_CLIENT._base_url + "/timeseries/data", status=200, json={})
    yield rsps


class TestInsertDatapoints:
    def test_insert_tuples(self, mock_post_datapoints):
        dps = [(i * 1e10, i) for i in range(1, 11)]
        DPS_CLIENT.insert(dps, id=1)
        assert {
            "items": {"id": 1, "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 11)]}
        } == jsgz_load(mock_post_datapoints.calls[0].request.body)

    def test_insert_dicts(self, mock_post_datapoints):
        dps = [{"timestamp": i * 1e10, "value": i} for i in range(1, 11)]
        DPS_CLIENT.insert(dps, id=1)
        assert {
            "items": {"id": 1, "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 11)]}
        } == jsgz_load(mock_post_datapoints.calls[0].request.body)

    def test_by_external_id(self, mock_post_datapoints):
        dps = [(i * 1e10, i) for i in range(1, 11)]
        DPS_CLIENT.insert(dps, external_id="1")
        assert {
            "items": {"externalId": "1", "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 11)]}
        } == jsgz_load(mock_post_datapoints.calls[0].request.body)

    def test_insert_datapoints_in_jan_1970(self):
        dps = [{"timestamp": i, "value": i} for i in range(1, 11)]
        with pytest.raises(AssertionError):
            DPS_CLIENT.insert(dps, id=1)

    @pytest.mark.parametrize("ts_key, value_key", [("timestamp", "values"), ("timstamp", "value")])
    def test_invalid_datapoints_keys(self, ts_key, value_key):
        dps = [{ts_key: i * 1e10, value_key: i} for i in range(1, 11)]
        with pytest.raises(AssertionError, match="is missing the"):
            DPS_CLIENT.insert(dps, id=1)

    def test_insert_datapoints_over_limit(self, set_dps_limits, mock_post_datapoints):
        set_dps_limits(5)
        dps = [(i * 1e10, i) for i in range(1, 11)]
        DPS_CLIENT.insert(dps, id=1)
        request_bodies = [jsgz_load(call.request.body) for call in mock_post_datapoints.calls]
        assert {
            "items": {"id": 1, "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 6)]}
        } in request_bodies
        assert {
            "items": {"id": 1, "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(6, 11)]}
        } in request_bodies

    def test_insert_datapoints_no_data(self):
        with pytest.raises(AssertionError, match="No datapoints provided"):
            DPS_CLIENT.insert(id=1, datapoints=[])

    def test_insert_datapoints_in_multiple_time_series(self, mock_post_datapoints):
        dps = [{"timestamp": i * 1e10, "value": i} for i in range(1, 11)]
        dps_objects = [{"externalId": "1", "datapoints": dps}, {"id": 1, "datapoints": dps}]
        DPS_CLIENT.insert_multiple(dps_objects)
        request_bodies = [jsgz_load(call.request.body) for call in mock_post_datapoints.calls]
        assert {
            "items": {"id": 1, "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 11)]}
        } in request_bodies
        assert {
            "items": {"externalId": "1", "datapoints": [{"timestamp": int(i * 1e10), "value": i} for i in range(1, 11)]}
        } in request_bodies

    def test_insert_datapoints_in_multiple_time_series_invalid_key(self):
        dps = [{"timestamp": i * 1e10, "value": i} for i in range(1, 11)]
        dps_objects = [{"extId": "1", "datapoints": dps}]
        with pytest.raises(AssertionError, match="Invalid key 'extId'"):
            DPS_CLIENT.insert_multiple(dps_objects)


class TestDatapointsObject:
    def test_len(self):
        assert 3 == len(Datapoints(id=1, timestamp=[1, 2, 3], value=[1, 2, 3]))

    def test_get_operative_attrs(self):
        assert [("timestamp", [1, 2, 3]), ("value", [1, 2, 3])] == list(
            Datapoints(id=1, timestamp=[1, 2, 3], value=[1, 2, 3])._get_operative_attrs()
        )
        assert sorted([("timestamp", [1, 2, 3]), ("max", [1, 2, 3]), ("sum", [1, 2, 3])]) == sorted(
            list(Datapoints(id=1, timestamp=[1, 2, 3], sum=[1, 2, 3], max=[1, 2, 3])._get_operative_attrs())
        )
        assert [("timestamp", [])] == list(Datapoints(id=1)._get_operative_attrs())

    def test_load(self):
        res = Datapoints._load(
            {"id": 1, "externalId": "1", "datapoints": [{"timestamp": 1, "value": 1}, {"timestamp": 2, "value": 2}]}
        )
        assert 1 == res.id
        assert "1" == res.external_id
        assert [1, 2] == res.timestamp
        assert [1, 2] == res.value

    def test_truncate(self):
        res = Datapoints(id=1, timestamp=[1, 2, 3])._truncate(limit=1)
        assert [1] == res.timestamp


class TestHelpers:
    @pytest.mark.parametrize(
        "start, end, granularity, num_of_workers, expected_output",
        [
            (1550241236999, 1550244237001, "1d", 1, [_DPWindow(1550241236999, 1550244237001)]),
            (0, 10000, "1s", 10, [_DPWindow(i, i + 1000) for i in range(0, 10000, 2000)]),
            (0, 2500, "1s", 3, [_DPWindow(0, 1250), _DPWindow(2250, 2500)]),
            (0, 2500, None, 3, [_DPWindow(0, 833), _DPWindow(834, 1667), _DPWindow(1668, 2500)]),
        ],
    )
    def test_get_datapoints_windows(self, start, end, granularity, num_of_workers, expected_output):
        res = DPS_CLIENT._get_windows(start=start, end=end, granularity=granularity, max_windows=num_of_workers)
        assert expected_output == res

    def test_concatenate_datapoints(self):
        d1 = Datapoints(id=1, external_id="1", timestamp=[1, 2, 3], value=[1, 2, 3])
        d2 = Datapoints(id=1, external_id="1", timestamp=[4, 5, 6], value=[4, 5, 6])
        concatenated = DPS_CLIENT._concatenate_datapoints(d1, d2)
        assert [1, 2, 3, 4, 5, 6] == concatenated.timestamp
        assert [1, 2, 3, 4, 5, 6] == concatenated.value
        assert 1 == concatenated.id
        assert "1" == concatenated.external_id
        assert concatenated.sum is None

    @pytest.mark.parametrize(
        "ids, external_ids, expected_output",
        [
            (1, None, ([{"id": 1}], True)),
            (None, "1", ([{"externalId": "1"}], True)),
            (1, "1", ([{"id": 1}, {"externalId": "1"}], False)),
            ([1], ["1"], ([{"id": 1}, {"externalId": "1"}], False)),
            ([1], None, ([{"id": 1}], False)),
            ({"id": 1, "aggregates": ["average"]}, None, ([{"id": 1, "aggregates": ["average"]}], True)),
            ({"id": 1}, {"externalId": "1"}, ([{"id": 1}, {"externalId": "1"}], False)),
            (
                [{"id": 1, "aggregates": ["average"]}],
                [{"externalId": "1", "aggregates": ["average", "sum"]}],
                ([{"id": 1, "aggregates": ["average"]}, {"externalId": "1", "aggregates": ["average", "sum"]}], False),
            ),
        ],
    )
    def test_process_time_series_input_ok(self, ids, external_ids, expected_output):
        assert expected_output == DPS_CLIENT._process_ts_identifiers(ids, external_ids)

    @pytest.mark.parametrize(
        "ids, external_ids, exception, match",
        [
            (1.0, None, TypeError, "Invalid type '<class 'float'>'"),
            ([1.0], None, TypeError, "Invalid type '<class 'float'>'"),
            (None, 1, TypeError, "Invalid type '<class 'int'>'"),
            (None, [1], TypeError, "Invalid type '<class 'int'>'"),
            ({"wrong": 1, "aggregates": ["average"]}, None, ValueError, "Unknown key 'wrong'"),
            (None, [{"externalId": 1, "wrong": ["average"]}], ValueError, "Unknown key 'wrong'"),
            (None, {"id": 1, "aggregates": ["average"]}, ValueError, "Unknown key 'id'"),
            ({"externalId": 1}, None, ValueError, "Unknown key 'externalId'"),
        ],
    )
    def test_process_time_series_input_fail(self, ids, external_ids, exception, match):
        with pytest.raises(exception, match=match):
            DPS_CLIENT._process_ts_identifiers(ids, external_ids)

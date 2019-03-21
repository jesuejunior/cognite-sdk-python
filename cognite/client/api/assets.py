# -*- coding: utf-8 -*-
import json
from typing import *

import pandas as pd

from cognite.client._utils.api_client import APIClient
from cognite.client._utils.resource_base import CogniteResource, CogniteResourceList


# GenClass: AssetV2
class Asset(CogniteResource):
    """Representation of a physical asset, e.g plant or piece of equipment

    Args:
        id (int): ID of the asset.
        path (List[int]): IDs of assets on the path to the asset.
        depth (int): Asset path depth (number of levels below root node).
        name (str): Name of asset. Often referred to as tag.
        parent_id (int): ID of parent asset, if any
        description (str): Description of asset.
        types (List[Dict[str, Any]]): The field specific values of the asset.
        metadata (Dict[str, Any]): Custom, application specific metadata. String key -> String value
        source (str): The source of this asset
        source_id (str): ID of the asset in the source. Only applicable if source is specified. The combination of source and sourceId must be unique.
        created_time (int): Time when this asset was created in CDP in milliseconds since Jan 1, 1970.
        last_updated_time (int): The last time this asset was updated in CDP, in milliseconds since Jan 1, 1970.
    """

    def __init__(
        self,
        id: int = None,
        path: List[int] = None,
        depth: int = None,
        name: str = None,
        parent_id: int = None,
        description: str = None,
        types: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        source: str = None,
        source_id: str = None,
        created_time: int = None,
        last_updated_time: int = None,
    ):
        self.id = id
        self.path = path
        self.depth = depth
        self.name = name
        self.parent_id = parent_id
        self.description = description
        self.types = types
        self.metadata = metadata
        self.source = source
        self.source_id = source_id
        self.created_time = created_time
        self.last_updated_time = last_updated_time

    # GenStop


class AssetList(CogniteResourceList):
    _RESOURCE = Asset


class AssetsApi(APIClient):
    RESOURCE_PATH = "/assets"

    def get(self, id: Union[int, List[int]]) -> Union[Asset, AssetList]:
        """Get assets by id

        Args:
            id (Union[int, List[int]): Id or list of ids
        Returns:
            Union[Asset, AssetList]: Requested asset(s)
        """

        return self._retrieve(AssetList, self.RESOURCE_PATH, id)

    # GenMethod: getAssets -> AssetList
    def list(
        self,
        name: str = None,
        depth: int = None,
        metadata: str = None,
        description: str = None,
        source: str = None,
        limit: int = None,
    ) -> AssetList:
        """List all assets

Retrieve a list of all assets in the given project. The list is sorted alphabetically
by name. This operation supports pagination. You can retrieve a subset of assets
by supplying additional fields; Only assets satisfying all criteria will be returned.
Names and descriptions are fuzzy searched using [edit distance](https://en.wikipedia.org/wiki/Edit_distance).
The fuzziness parameter controls the maximum edit distance when considering matches

        Args:
            name (str): The name of the asset(s) to get.
            depth (int): Get sub assets up to this many levels below the specified path.
            metadata (str): The metadata values used to filter the results. Format is {"key1": "value1", "key2": "value2"}. The maximum number of entries (pairs of key+value) is 64. The maximum length in characters of the sum of all keys and values is 10240. There is also a maximum length of 128 characters per key and 512 per value.
            description (str): Only return assets that contain this description
            source (str): The source of the assets used to filter the results
            limit (int): Limits the number of results to be returned. The maximum results returned by the server is 1000 even if the limit specified is larger.

        Returns:
            AssetList:
        """
        # GenStop
        return

    def iter(self):
        return

    def create(self, asset: Union[Asset, List[Asset]]) -> Union[Asset, AssetList]:
        """Create one or more assets.

        Args:
            asset (Union[Asset, List[Asset]]): Asset or list of assets to create.
        Returns:
            Union[Asset, AssetList]: Created asset(s)
        """
        return

    def delete(self):
        return

    def update(self):
        return

    def search(self):
        return

    def get_subtree(self):
        return

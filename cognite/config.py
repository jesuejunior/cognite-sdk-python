# -*- coding: utf-8 -*-
'''Project Configuration Module.

This module allows you to set an api-key and a project for your python project.
'''
import inspect
import re

from cognite._constants import BASE_URL, RETRY_LIMIT

_CONFIG_API_KEY = ''
_CONFIG_PROJECT = ''
_CONFIG_COOKIES = {}
_CONFIG_BASE_URL = None
_CONFIG_RETRIES = None


def configure_session(api_key='', project='', cookies=None):
    '''Sets session variables.

    Args:
        api_key (str):  Api-key for current project.

        cookies (dict): Cookies to pass with requests.

        project (str):  Project name for current project.
    '''
    global _CONFIG_API_KEY, _CONFIG_COOKIES, _CONFIG_PROJECT
    _CONFIG_API_KEY = api_key
    _CONFIG_PROJECT = project
    _CONFIG_COOKIES = {} if cookies is None else cookies


def get_config_variables(api_key, project):
    '''Returns current project config variables unless other is specified.

    Args:
        api_key (str):  Other specified api-key.

        project (str):  Other specified project name.

    Returns:
        tuple: api-key and project name belonging to current project unless other is specified.
    '''
    if api_key is None:
        api_key = _CONFIG_API_KEY
    if project is None:
        project = _CONFIG_PROJECT
    return api_key, project


def get_cookies():
    '''Returns cookies set for the current session.

    Returns:
        dict: Cookies for current session.
    '''
    return _CONFIG_COOKIES


def set_base_url(url=None):
    '''Sets the base url for requests made from the SDK.

    Args:
        url (str):  URL to set. Set this to None to use default url.
    '''
    global _CONFIG_BASE_URL
    _CONFIG_BASE_URL = url


def get_base_url():
    '''Returns the current base url for requests made from the SDK.

    Returns:
        str: current base url.
    '''
    frm = inspect.stack()[1]
    package_version = frm.filename.split('/')[-2]
    version = package_version[1] + '.' + package_version[2]
    if not re.match(r'^v\d\d$', package_version):
        version = '<version>'
    return BASE_URL + version if _CONFIG_BASE_URL is None else _CONFIG_BASE_URL


def set_number_of_retries(retries: int = None):
    '''Sets the number of retries attempted for requests made from the SDK.

    Args:
        retries (int):  Number of retries to attempt. Set this to None to use default num of retries.
    '''
    global _CONFIG_RETRIES
    _CONFIG_RETRIES = retries


def get_number_of_retries():
    '''Returns the current number of retries attempted for requests made from the SDK.

    Returns:
        int: current number of retries attempted for requests.
    '''
    return RETRY_LIMIT if _CONFIG_RETRIES is None else _CONFIG_RETRIES

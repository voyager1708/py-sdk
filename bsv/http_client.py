from abc import ABC, abstractmethod
from typing import Optional, Dict

import aiohttp
import requests


class HttpClient(ABC):
    @abstractmethod
    def fetch(self, url: str, options: dict) -> "HttpResponse":
        pass


class HttpResponse:
    def __init__(self, ok: bool, status_code: int, json_data: dict):
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class DefaultHttpClient(HttpClient):
    async def fetch(self, url: str, options: dict) -> HttpResponse:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method=options["method"],
                    url=url,
                    headers=options.get("headers", {}),
                    json=options.get("data", None),
            ) as response:
                try:
                    json_data = await response.json()
                    return HttpResponse(
                        ok=response.status >= 200 and response.status <= 299,
                        status_code=response.status,
                        json_data={
                            'data': json_data
                        },
                    )
                except Exception as e:
                    return HttpResponse(
                        ok=False,
                        status_code=response.status,
                        json_data={},
                    )


class SyncHttpClient:
    """
    Synchronous HTTP client for blocking operations
    """

    def __init__(self, default_timeout: int = 30):
        """
        Initialize synchronous HTTP client

        :param default_timeout: Default timeout setting in seconds
        """
        self.default_timeout = default_timeout

    def _make_response(self, response: requests.Response) -> HttpResponse:
        """
        Convert requests.Response to HttpResponse

        :param response: The requests Response object
        :returns: HttpResponse object
        """
        try:
            json_data = response.json()
        except ValueError:
            json_data = {}

        return HttpResponse(
            ok=response.ok,
            status_code=response.status_code,
            json_data=json_data
        )

    def _handle_error(self, error: requests.RequestException) -> HttpResponse:
        """
        Handle request errors and convert to HttpResponse

        :param error: The requests exception
        :returns: HttpResponse object with error information
        """
        # Set appropriate status code based on error type
        if isinstance(error, requests.Timeout):
            status_code = 408  # Request Timeout
        elif isinstance(error, requests.ConnectionError):
            status_code = 503  # Service Unavailable
        else:
            status_code = 0

        return HttpResponse(
            ok=False,
            status_code=status_code,
            json_data={"error": str(error), "error_type": type(error).__name__}
        )

    def fetch(self, url: str, options: dict) -> HttpResponse:
        """
        Send HTTP request synchronously

        :param url: The URL to request
        :param options: Request options (method, headers, data, timeout)
        :returns: HttpResponse object
        """
        method = options.get("method", "GET")
        headers = options.get("headers", {})
        timeout = options.get("timeout", self.default_timeout)

        try:
            if method.upper() == "POST":
                data = options.get("data", {})
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                response = requests.request(method, url, headers=headers, timeout=timeout)

            return self._make_response(response)
        except requests.RequestException as e:
            return self._handle_error(e)

    def get(self, url: str,
            headers: Optional[Dict[str, str]] = None,
            timeout: Optional[int] = None) -> HttpResponse:
        """
        Send GET request

        :param url: Request URL
        :param headers: HTTP headers
        :param timeout: Timeout setting in seconds (None uses default_timeout)
        :returns: HttpResponse object
        """
        try:
            request_timeout = timeout if timeout is not None else self.default_timeout
            response = requests.get(url, headers=headers or {}, timeout=request_timeout)
            return self._make_response(response)
        except requests.RequestException as e:
            return self._handle_error(e)


def default_http_client() -> HttpClient:
    return DefaultHttpClient()


def default_sync_http_client() -> SyncHttpClient:
    """
    Create default synchronous HTTP client

    :returns: SyncHttpClient instance
    """
    return SyncHttpClient()
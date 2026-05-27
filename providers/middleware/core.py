from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from providers.base import ProviderRequest, ProviderResponse

DispatchFunc = Callable[[ProviderRequest], Any]


class Middleware(ABC):
    @abstractmethod
    async def before(self, request: ProviderRequest) -> ProviderRequest: ...

    @abstractmethod
    async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse: ...


class MiddlewarePipeline:
    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def add(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    async def run(self, request: ProviderRequest, dispatch: DispatchFunc) -> ProviderResponse:
        for mw in self._middlewares:
            request = await mw.before(request)

        response = await dispatch(request)

        for mw in reversed(self._middlewares):
            response = await mw.after(request, response)

        return response

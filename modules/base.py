from playwright.async_api import Page
from typing import TYPE_CHECKING
from utils.logger import logger

if TYPE_CHECKING:
    from core.manager import HSRGameManager


class BaseModule:
    def __init__(self, manager: "HSRGameManager") -> None:
        self.manager = manager

    @property
    def page(self) -> Page:
        if self.manager.page is None:
            raise RuntimeError("浏览器页面 Page 对象未初始化，请先调用 init_browser()")
        return self.manager.page

    async def wait_for_request(
        self,
        url: str | list[str],
        timeout: int = 30000,
        after_listen: lambda: None = None,
    ) -> dict:
        logger.debug(f"正在监听请求: {url} (超时: {timeout}ms)")
        async with self.page.expect_response(
            lambda response: isinstance(url, str)
            and url in response.url
            or isinstance(url, list)
            and any(u in response.url for u in url),
            timeout=timeout,
        ) as response_info:
            if after_listen:
                logger.debug("正在执行 after_listen 回调...")
                await after_listen()
            response = await response_info.value
            logger.debug(f"捕获到请求响应: {response.url} (状态码: {response.status})")
            if response.status != 200:
                raise RuntimeError(f"请求 {url} 状态码异常: {response.status}")
            raw_json = await response.json()
            retcode = raw_json.get("retcode", -1)
            if retcode != 0:
                message = raw_json.get("message", "未知错误")
                raise RuntimeError(f"请求 {url} 异常({retcode}): {message}")
            return raw_json.get("data", {})

# core/manager.py
import os
from typing import Optional, Any
from playwright.async_api import Page, Browser, BrowserContext, Playwright
from utils.logger import logger
from utils.config_loader import AppConfig
from core.states import BaseState, CLIState, NotLoggedInState


class HSRGameManager:
    """
    崩铁云游戏全局状态机驱动器
    """

    playwright: Playwright
    browser: Optional[Browser]
    context: Optional[BrowserContext]
    page: Optional[Page]
    config: AppConfig
    state: BaseState

    def __init__(self, playwright: Playwright, config: AppConfig) -> None:
        self.playwright = playwright
        self.config = config
        self.browser = None
        self.context = None
        self.page = None

        self.state = NotLoggedInState()
        self.verify_task: Optional[Any] = None

        # 安全、独立导入解耦子模块
        from modules.login import LoginModule
        from modules.queue import QueueModule
        from modules.ingame import InGameModule

        self.login_mod = LoginModule(self)
        self.queue_mod = QueueModule(self)
        self.ingame_mod = InGameModule(self)

    async def init_browser(self, headless: bool = True) -> None:
        logger.debug("启动 Chromium 环境...")
        self.browser = await self.playwright.chromium.launch(headless=headless)

        cookie_file = self.config.account.cookie_path
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
        }

        if os.path.exists(cookie_file):
            logger.info("加载会话状态...")
            context_args["storage_state"] = cookie_file

        self.context = await self.browser.new_context(**context_args)
        self.context.set_default_timeout(5000)
        self.context.set_default_navigation_timeout(30000)
        self.page = await self.context.new_page()
        logger.success("浏览器环境启动成功")

    async def start_state_machine(self) -> None:
        while self.state is not None:
            try:
                next_state = await self.state.run(self)
                if next_state is not None:
                    logger.info(
                        f"[状态跃迁] {self.state.__class__.__name__} -> {next_state.__class__.__name__}"
                    )
                self.state = next_state
            except Exception as e:
                logger.exception(
                    f"状态机引擎在执行 {self.state.__class__.__name__} 时发生未捕获异常: {e}"
                )

                if os.getenv("GITHUB_ACTIONS") == "true":
                    raise e

                self.state = CLIState()

        logger.success("状态机引擎安全结束所有运行任务")

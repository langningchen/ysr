import asyncio
import sys
from playwright.async_api import async_playwright
from core.manager import HSRGameManager
from utils.config_loader import load_config
from utils.logger import logger


async def main() -> None:
    try:
        config = load_config("config.toml")
        logger.success("配置文件加载成功")
    except Exception as e:
        logger.error(f"配置文件解析链故障，程序初始化被迫中止! {e}")
        sys.exit(1)

    has_error = False

    async with async_playwright() as p:
        manager = HSRGameManager(p, config)
        await manager.init_browser(headless=True)

        try:
            await manager.start_state_machine()
        except Exception as e:
            logger.exception(f"在状态机内部发生了未捕获的致命中断: {e}")
            has_error = True
        finally:
            cookie_path = manager.config.account.cookie_path
            await manager.context.storage_state(path=cookie_path)
            await manager.close()

    if has_error:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

from utils.logger import logger
from modules.base import BaseModule


class LoginModule(BaseModule):
    async def navigate_to_portal(self) -> None:
        logger.info("导航至崩铁云游戏入口门户...")
        await self.page.goto("https://sr.mihoyo.com/cloud")

    async def check_logged_in(self) -> bool:
        logger.debug("正在验证当前登录状态...")
        try:
            response = await self.wait_for_request(
                "https://passport-api.mihoyo.com/account/ma-cn-session/web/webVerifyForGame"
            )
            logger.success(
                f"登录状态验证成功! UID: {response.get('user_info', {}).get('aid')} | {response.get('user_info', {}).get('mobile')}"
            )
            return True
        except Exception as e:
            logger.warning(f"登录状态验证失败: {e}")
            return False

    async def perform_login(self) -> None:
        logger.debug("正在执行登录流程...")
        login_iframe = self.page.frame_locator("#mihoyo-login-platform-iframe")

        username = self.manager.config.account.username
        password = self.manager.config.account.password
        await login_iframe.locator("#tab-password").click()
        await login_iframe.locator("#username").fill(username)
        await login_iframe.locator("#password").fill(password)
        await login_iframe.locator("#app > div > div > form > label").click()

        logger.debug("表单填写就绪，发送登录指令并监测服务端响应...")
        response = await self.wait_for_request(
            "https://passport-api.mihoyo.com/account/ma-cn-passport/web/loginByPassword",
            after_listen=lambda: login_iframe.locator(
                "#app > div > div > form > button"
            ).click(),
        )
        logger.success(
            f"登录成功! UID: {response.user_info.aid} | {response.user_info.mobile}"
        )

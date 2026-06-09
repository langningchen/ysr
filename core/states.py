from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import os
import sys
import traceback
from typing import Optional, TYPE_CHECKING
from utils.logger import logger

if TYPE_CHECKING:
    from core.manager import HSRGameManager


class BaseState(ABC):
    @abstractmethod
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        pass


class NotLoggedInState(BaseState):
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        await manager.login_mod.navigate_to_portal()
        is_logged_in = await manager.login_mod.check_logged_in()
        if not is_logged_in:
            await manager.login_mod.perform_login()
        return LoggedInState()


class LoggedInState(BaseState):
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        start_task = asyncio.create_task(manager.queue_mod.start())
        wait_task = asyncio.create_task(manager.queue_mod.wait_start())
        done, pending = await asyncio.wait(
            [start_task, wait_task], return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
        if start_task in done:
            exc = start_task.exception()
            if exc:
                logger.error("检测到排队操作流程发生异常！准备快速退出并保存 Trace...")
                raise exc
        return InGameState()


class InGameState(BaseState):
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        manager.ingame_mod.setup_locators()
        await manager.ingame_mod.dismiss_guides_and_agree_tos()

        clicked = await manager.ingame_mod.do_until_match(
            "phone.png",
            lambda: manager.ingame_mod.click_template("enter_game.png"),
            timeout_limit=60,
        )
        if not clicked:
            return ErrorState(f"点击进入游戏按钮失败")
        logger.success("游戏登录成功")

        return DailyWorkflowState()


class DailyWorkflowState(BaseState):
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        ingame = manager.ingame_mod

        async def handle_failure(reason: str) -> BaseState:
            logger.error(f"日常工作流异常: {reason}")
            return ErrorState(reason)
            # return CLIState()

        logger.info("打开星际和平指南...")
        success = await manager.ingame_mod.do_until_match(
            "targets.png",
            asyncio.gather(manager.ingame_mod.press_system_key("F4"), asyncio.sleep(2)),
        )
        if not success:
            return await handle_failure("打开星际和平指南失败")

        logger.info("选择培养目标...")
        success = await ingame.do_until_match(
            "enter.png",
            lambda: manager.ingame_mod.click_template(
                "targets.png",
            ),
        )
        if not success:
            return await handle_failure(
                "培养目标界面识别失败，未能找到 enter.png 进入挑战按钮。"
            )

        logger.debug("进入秘境...")
        success = await ingame.do_until_match(
            "plus.png",
            lambda: manager.ingame_mod.click_template(
                "enter.png",
            ),
        )
        if not success:
            return await handle_failure("挑战界面识别失败")

        logger.debug("增加挑战次数...")
        success = await ingame.do_until_match(
            "plus_disabled.png",
            lambda: manager.ingame_mod.click_template(
                "plus.png",
                threshold=0.95,
            ),
            timeout_limit=30.0,
        )

        logger.info("开始编队...")
        success = await ingame.do_until_match(
            "help.png",
            lambda: manager.ingame_mod.click_template(
                "start.png",
            ),
        )
        if not success:
            return await handle_failure("编队界面识别失败")

        logger.info("选择支援角色...")
        success = await ingame.do_until_match(
            "friend.png",
            lambda: manager.ingame_mod.click_template(
                "help.png",
            ),
        )
        if not success:
            return await handle_failure("支援列表识别失败")

        logger.info("选择朋友支援...")
        success = await ingame.do_until_match(
            "help_selected.png",
            lambda: asyncio.gather(
                manager.ingame_mod.click_template(
                    "friend.png",
                ),
                asyncio.sleep(2),
            ),
        )
        if not success:
            return await handle_failure("朋友支援选择失败")

        logger.info("确认支援角色...")
        success = await ingame.do_until_match(
            "confirm_start.png",
            lambda: manager.ingame_mod.click_template(
                "confirm.png",
            ),
        )
        if not success:
            return await handle_failure("确认支援角色失败")

        logger.info("开始挑战...")
        success = await ingame.do_until_match(
            "battle_started.png",
            lambda: manager.ingame_mod.click_template(
                "confirm_start.png",
            ),
        )
        if not success:
            return await handle_failure("开始挑战失败")

        logger.info("开启快速战斗模式...")
        await ingame.toggle_switch_on("fast_off.png", "fast_on.png")
        logger.debug("开启自动战斗模式...")
        await ingame.toggle_switch_on("auto_off.png", "auto_on.png")

        logger.info("等待战斗完成...")
        completed = await ingame.wait_for_template("done.png", timeout=300.0)
        if not completed:
            return await handle_failure("战斗阶段超时未完成，可能遭遇卡死或其他异常")

        logger.info("正在退出挑战结算流程...")
        success = await ingame.do_until_match(
            "close_page.png",
            lambda: manager.ingame_mod.click_template(
                "exit.png",
            ),
        )
        if not success:
            return await handle_failure("结算界面识别失败，未能找到退出按钮")

        logger.info("正在返回主界面...")
        success = await ingame.do_until_match(
            "phone.png",
            lambda: manager.ingame_mod.click_template(
                "close_page.png",
            ),
        )
        if not success:
            return await handle_failure("返回主界面失败")

        logger.info("正在调出手机菜单...")
        success = await ingame.do_until_match(
            "assigns.png",
            lambda: asyncio.gather(
                manager.ingame_mod.press_system_key("Escape"),
                asyncio.sleep(1.0),
            ),
        )
        if not success:
            return await handle_failure("无法调出手机菜单")

        logger.info("正在打开派遣界面...")
        success = await ingame.do_until_match(
            "assigns_claim.png",
            lambda: manager.ingame_mod.click_template(
                "assigns.png",
            ),
        )
        if not success:
            return await handle_failure("派遣界面识别失败")

        logger.info("正在领取派遣奖励...")
        success = await ingame.do_until_match(
            "close.png",
            lambda: manager.ingame_mod.click_template(
                "assigns_claim.png",
            ),
        )
        if not success:
            logger.warning("领取派遣奖励失败，忽略此错误")
        else:
            logger.info("正在确认领取到的奖励...")
            success = await ingame.do_until_match(
                "close_page.png",
                lambda: manager.ingame_mod.click_template(
                    "close.png",
                ),
            )
            if not success:
                return await handle_failure("派遣奖励确认失败")

        logger.info("正在关闭派遣界面...")
        success = await ingame.do_until_match(
            "open_tasks.png",
            lambda: manager.ingame_mod.click_template(
                "close_page.png",
            ),
        )
        if not success:
            return await handle_failure("无法关闭派遣界面")

        logger.info("正在返回主界面...")
        success = await ingame.do_until_match(
            "phone.png",
            lambda: manager.ingame_mod.click_template(
                "close_phone.png",
            ),
        )
        if not success:
            return await handle_failure("返回主界面失败")

        logger.info("开始处理日常任务领奖...")
        success = await manager.ingame_mod.do_until_match(
            "targets.png",
            asyncio.gather(manager.ingame_mod.press_system_key("F4"), asyncio.sleep(2)),
        )
        if not success:
            return await handle_failure("打开星际和平指南失败")

        logger.debug("正在循环领取日常阶段奖励...")
        success = await ingame.do_until_match(
            "claimed_all.png",
            lambda: manager.ingame_mod.click_template(
                "claim.png",
            ),
            timeout_limit=30.0,
        )
        if not success:
            return await handle_failure("未找到可领取的日常任务奖励")

        logger.debug("正在领取最终奖励...")
        success = await ingame.do_until_match(
            "close.png",
            lambda: manager.ingame_mod.click_template(
                "get_awards.png",
            ),
        )
        if not success:
            return await handle_failure("领取最终奖励失败")

        logger.success("日常工作流完成")
        return None


class CLIState(BaseState):
    async def run(self, manager: HSRGameManager) -> Optional[BaseState]:
        page = manager.page
        ingame = manager.ingame_mod

        await self._async_repl({"manager": manager, "page": page, "ingame": ingame})
        return None

    async def _async_repl(self, local_vars: dict) -> None:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "HSR-REPL >>> ")
                user_input = user_input.strip()
                if user_input in ["exit()", "quit()", "exit", "quit"]:
                    break
                if not user_input:
                    continue
                if user_input.startswith("await "):
                    user_input = user_input[6:].strip()

                try:
                    result = eval(user_input, globals(), local_vars)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if result is not None:
                        print(repr(result))
                except SyntaxError:
                    exec(user_input, globals(), local_vars)
            except KeyboardInterrupt:
                print("\n输入 exit() 退出。")
            except Exception:
                traceback.print_exc(file=sys.stdout)


class ErrorState(BaseState):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def run(self, _: HSRGameManager) -> Optional[BaseState]:
        logger.error(f"状态机遭遇异常: {self.reason}")

        if os.getenv("GITHUB_ACTIONS") == "true":
            raise RuntimeError(f"GitHub Actions 运行期间发生致命错误: {self.reason}")

        return CLIState()

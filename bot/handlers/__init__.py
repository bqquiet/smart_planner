from aiogram import Router

from .commands import router as commands_router
from .add_task import router as add_task_router
from .edit_task import router as edit_task_router
from .search import router as search_router
from .ai_task import router as ai_task_router
from .callbacks import router as callbacks_router


def get_all_routers() -> list[Router]:
    # FSM routers first — order matters for state priority
    return [
        ai_task_router,
        add_task_router,
        edit_task_router,
        search_router,
        commands_router,
        callbacks_router,
    ]

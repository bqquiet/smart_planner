from aiogram.fsm.state import State, StatesGroup


class AddTaskFSM(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_priority = State()
    waiting_category = State()
    waiting_repeat = State()
    waiting_deadline = State()


class EditTaskFSM(StatesGroup):
    choose_field = State()
    waiting_new_title = State()
    waiting_new_description = State()
    waiting_new_priority = State()
    waiting_new_category = State()
    waiting_new_repeat = State()
    waiting_new_deadline = State()


class SearchFSM(StatesGroup):
    waiting_query = State()


class AITaskFSM(StatesGroup):
    waiting_text = State()       # user types free-form task
    confirm_parsed = State()     # user confirms/edits AI result
    waiting_subtasks = State()   # user asked to generate subtasks

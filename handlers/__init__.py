from .start_handler import start_handler
from .error_handler import error_handler
from .common_handler import message_handler
from .user_handler import (
    search_by_name_handler,
    search_by_genre_handler,
    search_by_year_handler,
    ai_assistant_handler
)
from .history_handler import history_handler
from .top_handler import top_handler
from .inline_query_handler import inline_query_handler, inline_movie_command_handler

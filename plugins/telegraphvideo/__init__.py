from app.plugins import _PluginBase


class TelegraphVideo(_PluginBase):
    # Plugin metadata must stay in sync with package.json and package.v2.json.
    plugin_name = "Telegraph Video"
    plugin_desc = "Telegraph Video MP 接入插件骨架，用于后续接管 STRM 与同步媒体资源。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/Moviepilot_A.png"
    plugin_version = "0.1.0"
    plugin_author = "telegraph-video"
    plugin_config_prefix = "telegraphvideo_"
    plugin_order = 1
    auth_level = 1

    def init_plugin(self, config: dict = None):
        self._config = config or {}

    def get_state(self) -> bool:
        return False

    @staticmethod
    def get_command() -> list:
        return []

    def get_api(self) -> list:
        return []

    def get_service(self) -> list:
        return []

    def get_form(self) -> tuple[list, dict]:
        return [], {}

    def get_page(self) -> list:
        return []

    def stop_service(self):
        pass

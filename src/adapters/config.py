from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", frozen=True)

    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    chroma_persist_dir: str = "./data/chroma_db"
    sqlite_db_path: str = "./data/agent_memory.db"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    upload_dir: str = "./data/uploads"
    upload_max_size_mb: int = 20
    audio_upload_dir: str = "./data/audio_uploads"
    audio_max_size_mb: int = 50
    video_upload_dir: str = "./data/video_uploads"
    video_max_size_mb: int = 200
    video_keyframe_interval: int = 5  # 关键帧抽取间隔（秒）
    agent_max_tool_rounds: int = 5
    agent_short_term_size: int = 20
    agent_context_window: int = 6  # Context Builder 保留最近 N 轮

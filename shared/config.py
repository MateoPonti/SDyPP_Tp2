from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 2
    node_id: int = 1
    peers: str = ""
    heartbeat_interval: float = 1.0
    startup_delay: float = 1.0
    task_network: str = "tp2-task-network"
    task_timeout_seconds: float = 30.0
    task_service_port: int = 8080
    log_file: str = "logs/server.log"
    executor: str = "local"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def peer_urls(self) -> list[str]:
        return [
            peer.strip().split("=", 1)[-1].rstrip("/")
            for peer in self.peers.split(",")
            if peer.strip()
        ]

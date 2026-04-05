"""[已弃用] 基于文件的 ForeshadowingRegistry 仓储。

生产路径请使用 :class:`infrastructure.persistence.database.sqlite_foreshadowing_repository.SqliteForeshadowingRepository`。
保留本模块仅供一次性从 JSON 迁移或本地脚本导入。
"""
import logging
from typing import Optional
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from infrastructure.persistence.storage.backend import StorageBackend
from infrastructure.persistence.mappers.foreshadowing_mapper import ForeshadowingMapper

logger = logging.getLogger(__name__)


class FileForeshadowingRepository(ForeshadowingRepository):
    """基于文件系统的 ForeshadowingRegistry 仓储实现

    使用 JSON 文件存储伏笔注册表数据。
    """

    def __init__(self, storage: StorageBackend):
        """初始化仓储

        Args:
            storage: 存储后端
        """
        self.storage = storage

    def _get_path(self, novel_id: NovelId) -> str:
        """获取伏笔注册表文件路径

        Args:
            novel_id: 小说 ID

        Returns:
            文件路径
        """
        return f"foreshadowings/{novel_id.value}.json"

    def save(self, registry: ForeshadowingRegistry) -> None:
        """保存伏笔注册表"""
        path = self._get_path(registry.novel_id)
        data = ForeshadowingMapper.to_dict(registry)
        self.storage.write_json(path, data)

    def get_by_novel_id(self, novel_id: NovelId) -> Optional[ForeshadowingRegistry]:
        """根据小说 ID 获取伏笔注册表"""
        path = self._get_path(novel_id)

        if not self.storage.exists(path):
            return None

        data = self.storage.read_json(path)
        return ForeshadowingMapper.from_dict(data)

    def delete(self, novel_id: NovelId) -> None:
        """删除伏笔注册表"""
        path = self._get_path(novel_id)
        self.storage.delete(path)

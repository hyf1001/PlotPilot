# Superpowers 全集成规划 v2.0

**基于现有前端组件的优化方案**

---

## 🎯 核心策略

**不创建新组件，只优化现有的！**

前端已有完善的组件：
- ✅ BiblePanel - 作品设定
- ✅ KnowledgePanel - 侧栏资料（梗概、分章叙事、三元组、检索）
- ✅ ConsistencyReportPanel - 一致性报告
- ✅ CastGraphCompact - 人物关系图
- ✅ KnowledgeTripleGraph - 三元组图谱

**只需让后端功能真正工作，数据自动流入前端！**

---

## 📋 Phase 1: 核心数据流（最高优先级）⭐⭐⭐

### 目标
生成章节后自动提取和更新 Bible、Knowledge 数据

### 1.1 集成 StateExtractor

**文件**: `application/workflows/auto_novel_generation_workflow.py`

**修改点 1**: 添加依赖注入
```python
def __init__(
    self,
    # ... 现有参数
    state_extractor: StateExtractor,  # 新增
    state_updater: StateUpdater,      # 新增
):
    # ...
    self.state_extractor = state_extractor
    self.state_updater = state_updater
```

**修改点 2**: 修改 `_extract_chapter_state` 方法
```python
def _extract_chapter_state(self, content: str, chapter_number: int) -> ChapterState:
    """从生成的内容中提取章节状态"""
    # 当前：返回空状态
    # 修改为：调用 StateExtractor
    return self.state_extractor.extract(content, chapter_number)
```

**文件**: `interfaces/api/dependencies.py`

**添加**:
```python
def get_state_extractor() -> StateExtractor:
    return StateExtractor(
        llm_service=get_llm_service()
    )

def get_state_updater() -> StateUpdater:
    return StateUpdater(
        bible_repository=get_bible_repository(),
        knowledge_repository=get_knowledge_repository(),
        cast_repository=get_cast_repository()
    )
```

**修改 `get_auto_novel_generation_workflow`**:
```python
def get_auto_novel_generation_workflow(...) -> AutoNovelGenerationWorkflow:
    return AutoNovelGenerationWorkflow(
        # ... 现有参数
        state_extractor=get_state_extractor(),
        state_updater=get_state_updater(),
    )
```

### 1.2 集成 StateUpdater

**文件**: `application/workflows/auto_novel_generation_workflow.py`

**修改点**: 在 `generate_chapter` 和 `generate_chapter_stream` 的 Phase 4 后添加
```python
# Phase 4: Post-Generation
chapter_state = self._extract_chapter_state(content, chapter_number)
consistency_report = self._check_consistency(chapter_state, novel_id)

# Phase 4.5: Update State (新增)
logger.info(f"Updating Bible and Knowledge for chapter {chapter_number}")
self.state_updater.update(novel_id, chapter_number, chapter_state)
logger.info("State update completed")
```

### 1.3 修复 ConsistencyChecker 数据加载

**文件**: `application/workflows/auto_novel_generation_workflow.py`

**修改点**: `_check_consistency` 方法
```python
def _check_consistency(self, chapter_state: ChapterState, novel_id: str) -> ConsistencyReport:
    """检查章节一致性"""
    # 当前：创建空的临时对象
    # 修改为：从仓储加载真实数据

    # 1. 加载 Bible
    bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
    if not bible:
        bible = Bible(id=f"temp-{novel_id}", novel_id=NovelId(novel_id))

    # 2. 加载 CharacterRegistry
    character_registry = self._load_character_registry(novel_id, bible)

    # 3. 加载 ForeshadowingRegistry
    foreshadowing_registry = self.foreshadowing_repository.get_by_novel_id(NovelId(novel_id))
    if not foreshadowing_registry:
        foreshadowing_registry = ForeshadowingRegistry(id=f"temp-{novel_id}")

    # 4. 加载 Knowledge
    knowledge = self.knowledge_repository.get_by_novel_id(NovelId(novel_id))
    if not knowledge:
        knowledge = StoryKnowledge(id=f"temp-{novel_id}", novel_id=NovelId(novel_id))

    # 5. 构建上下文
    context = ConsistencyContext(
        bible=bible,
        character_registry=character_registry,
        foreshadowing_registry=foreshadowing_registry,
        knowledge=knowledge,
        previous_chapters=self._load_previous_chapters(novel_id)
    )

    # 6. 执行检查
    return self.consistency_checker.check_all(chapter_state, context)

def _load_character_registry(self, novel_id: str, bible: Bible) -> CharacterRegistry:
    """从 Bible 构建 CharacterRegistry"""
    registry = CharacterRegistry(id=f"{novel_id}-registry", novel_id=novel_id)

    for char in bible.characters:
        # 根据角色定位推断重要性
        importance = self._infer_character_importance(char)
        registry.register_character(char, importance)

    return registry

def _infer_character_importance(self, char) -> CharacterImportance:
    """根据角色定位推断重要性"""
    role = (char.role or "").lower()
    if any(k in role for k in ["主角", "protagonist", "主人公"]):
        return CharacterImportance.PROTAGONIST
    elif any(k in role for k in ["主要", "major", "核心"]):
        return CharacterImportance.MAJOR
    elif any(k in role for k in ["次要", "supporting", "配角"]):
        return CharacterImportance.SUPPORTING
    else:
        return CharacterImportance.MINOR

def _load_previous_chapters(self, novel_id: str) -> list:
    """加载之前的章节"""
    # 从 chapter_repository 加载
    return []  # 简化实现
```

**预期效果**:
- ✅ 生成章节后自动提取人物、关系、事件
- ✅ 自动更新 Bible 和 Knowledge 数据
- ✅ 一致性检查使用真实数据，返回有意义的报告
- ✅ 前端 KnowledgePanel 自动显示新数据
- ✅ 前端 ConsistencyReportPanel 显示真实报告

---

## 📋 Phase 2: 向量检索基础设施（高优先级）⭐⭐

### 目标
启用 KnowledgePanel 的检索功能

### 2.1 配置环境变量

**文件**: `.env` (或 `.env.local`)

**添加**:
```bash
# OpenAI API (用于 Embedding)
OPENAI_API_KEY=sk-...

# Qdrant 向量数据库
QDRANT_URL=http://localhost:6333
```

### 2.2 启动 Qdrant 服务

**Docker Compose**:
```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
```

**启动**:
```bash
docker-compose up -d qdrant
```

### 2.3 注册服务

**文件**: `interfaces/api/dependencies.py`

**添加**:
```python
import os
from infrastructure.ai.openai_embedding_service import OpenAIEmbeddingService
from infrastructure.ai.qdrant_vector_store import QdrantVectorStore
from application.services.indexing_service import IndexingService

def get_embedding_service() -> EmbeddingService | None:
    """获取 Embedding 服务"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, embedding disabled")
        return None
    return OpenAIEmbeddingService(api_key)

def get_vector_store() -> VectorStore | None:
    """获取向量存储"""
    # 当前返回 None，修改为返回真实实例
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_service = get_embedding_service()

    if not embedding_service:
        logger.warning("Embedding service not available, vector store disabled")
        return None

    try:
        return QdrantVectorStore(qdrant_url, embedding_service)
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}")
        return None

def get_indexing_service() -> IndexingService:
    """获取索引服务"""
    return IndexingService(
        vector_store=get_vector_store(),
        chapter_repository=get_chapter_repository(),
        knowledge_repository=get_knowledge_repository()
    )
```

### 2.4 创建索引 API 端点

**文件**: `interfaces/api/v1/indexing.py` (新建)

```python
from fastapi import APIRouter, Depends, HTTPException
from application.services.indexing_service import IndexingService
from interfaces.api.dependencies import get_indexing_service

router = APIRouter(prefix="/novels/{novel_id}/index", tags=["indexing"])

@router.post("", status_code=202)
async def index_novel(
    novel_id: str,
    service: IndexingService = Depends(get_indexing_service)
):
    """索引整本小说的所有章节"""
    if not service.vector_store:
        raise HTTPException(503, "Vector store not available")

    try:
        await service.index_novel(novel_id)
        return {"message": "Indexing started"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/chapters/{chapter_number}", status_code=202)
async def index_chapter(
    novel_id: str,
    chapter_number: int,
    service: IndexingService = Depends(get_indexing_service)
):
    """索引单个章节"""
    if not service.vector_store:
        raise HTTPException(503, "Vector store not available")

    try:
        await service.index_chapter(novel_id, chapter_number)
        return {"message": "Chapter indexed"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("", status_code=204)
async def clear_index(
    novel_id: str,
    service: IndexingService = Depends(get_indexing_service)
):
    """清空小说的索引"""
    if not service.vector_store:
        raise HTTPException(503, "Vector store not available")

    try:
        await service.clear_index(novel_id)
    except Exception as e:
        raise HTTPException(500, str(e))
```

**注册路由**: `interfaces/api/v1/__init__.py`
```python
from .indexing import router as indexing_router

# 在 create_api_router 中添加
api_router.include_router(indexing_router)
```

### 2.5 增强 Knowledge 检索端点

**文件**: `interfaces/api/v1/knowledge.py`

**修改**: `search_knowledge` 端点使用向量检索
```python
@router.post("/{novel_id}/search")
async def search_knowledge(
    novel_id: str,
    query: str,
    limit: int = 8,
    service: KnowledgeService = Depends(get_knowledge_service),
    indexing_service: IndexingService = Depends(get_indexing_service)
):
    """检索知识（使用向量检索）"""
    try:
        # 如果有向量存储，使用向量检索
        if indexing_service.vector_store:
            results = await indexing_service.search(novel_id, query, limit)
            return {"hits": results}

        # 否则降级到关键词检索
        knowledge = service.get_knowledge(novel_id)
        # ... 现有的关键词检索逻辑
    except Exception as e:
        raise HTTPException(500, str(e))
```

**预期效果**:
- ✅ KnowledgePanel 的检索功能真正工作
- ✅ 支持语义搜索章节、人物、事件
- ✅ 章节生成后自动索引（在 StateUpdater 中调用）

---

## 📋 Phase 3: 智能人物管理（中优先级）⭐

### 目标
启用人物分层管理和智能出场调度

### 3.1 集成 CharacterIndexer

**文件**: `interfaces/api/dependencies.py`

**添加**:
```python
from application.services.character_indexer import CharacterIndexer

def get_character_indexer() -> CharacterIndexer | None:
    """获取人物索引器"""
    vector_store = get_vector_store()
    embedding_service = get_embedding_service()

    if not vector_store or not embedding_service:
        return None

    return CharacterIndexer(
        vector_store=vector_store,
        embedding_service=embedding_service
    )
```

### 3.2 集成 AppearanceScheduler

**文件**: `application/services/context_builder.py`

**修改点 1**: 添加依赖
```python
from domain.bible.services.appearance_scheduler import AppearanceScheduler

def __init__(
    self,
    # ... 现有参数
    appearance_scheduler: AppearanceScheduler | None = None,  # 新增
    character_indexer: CharacterIndexer | None = None,        # 新增
):
    # ...
    self.appearance_scheduler = appearance_scheduler
    self.character_indexer = character_indexer
```

**修改点 2**: 在 `build_context` 中使用
```python
def build_context(self, novel_id: str, chapter_number: int, outline: str, max_tokens: int = 35000) -> str:
    """构建章节生成上下文"""

    # 1. 如果有 AppearanceScheduler，调度人物出场
    scheduled_characters = []
    if self.appearance_scheduler:
        scheduled_characters = self.appearance_scheduler.schedule_appearances(
            novel_id, chapter_number, outline
        )

    # 2. 构建各层上下文
    layer1 = self._build_layer1_core_context(novel_id, chapter_number, outline, layer1_budget)
    layer2 = self._build_layer2_smart_retrieval(
        novel_id, chapter_number, outline, layer2_budget,
        scheduled_characters=scheduled_characters  # 传入调度结果
    )
    # ...
```

**修改点 3**: 在 `_build_layer2_smart_retrieval` 中使用 CharacterIndexer
```python
def _build_layer2_smart_retrieval(
    self,
    novel_id: str,
    chapter_number: int,
    outline: str,
    max_tokens: int,
    scheduled_characters: list = None
) -> str:
    """Layer 2: 智能检索角色和关系"""

    # 1. 如果有调度结果，优先使用
    if scheduled_characters:
        characters = scheduled_characters
    # 2. 否则使用 CharacterIndexer 语义搜索
    elif self.character_indexer:
        characters = self.character_indexer.search_relevant_characters(
            novel_id, outline, top_k=5
        )
    # 3. 降级：从 Bible 加载所有角色
    else:
        bible = self.bible_service.get_bible(novel_id)
        characters = bible.characters if bible else []

    # ... 构建角色信息
```

**文件**: `interfaces/api/dependencies.py`

**修改 `get_context_builder`**:
```python
def get_context_builder() -> ContextBuilder:
    return ContextBuilder(
        bible_service=get_bible_service(),
        storyline_manager=get_storyline_manager(),
        relationship_engine=get_relationship_engine(),
        vector_store=get_vector_store(),
        appearance_scheduler=get_appearance_scheduler(),  # 新增
        character_indexer=get_character_indexer(),        # 新增
    )

def get_appearance_scheduler() -> AppearanceScheduler | None:
    """获取出场调度器"""
    # 简化实现：返回默认实例
    return AppearanceScheduler()
```

**预期效果**:
- ✅ 人物按重要性分层管理
- ✅ 智能选择出场人物
- ✅ 基于语义搜索相关人物
- ✅ 前端 BiblePanel 显示的人物会被智能使用

---

## 📋 Phase 4: 自动索引（中优先级）⭐

### 目标
生成章节后自动索引到向量数据库

### 4.1 在 StateUpdater 中添加索引

**文件**: `application/services/state_updater.py`

**修改点**: 添加 IndexingService 依赖
```python
from application.services.indexing_service import IndexingService

class StateUpdater:
    def __init__(
        self,
        bible_repository: BibleRepository,
        knowledge_repository: KnowledgeRepository,
        cast_repository: CastRepository,
        indexing_service: IndexingService | None = None,  # 新增
    ):
        # ...
        self.indexing_service = indexing_service

    def update(self, novel_id: str, chapter_number: int, chapter_state: ChapterState):
        """更新 Bible 和 Knowledge"""
        # 1. 更新 Bible
        self._update_bible(novel_id, chapter_state)

        # 2. 更新 Knowledge
        self._update_knowledge(novel_id, chapter_number, chapter_state)

        # 3. 更新 Cast
        self._update_cast(novel_id, chapter_state)

        # 4. 自动索引（新增）
        if self.indexing_service and self.indexing_service.vector_store:
            try:
                self.indexing_service.index_chapter(novel_id, chapter_number)
                logger.info(f"Chapter {chapter_number} indexed successfully")
            except Exception as e:
                logger.warning(f"Failed to index chapter {chapter_number}: {e}")
```

**文件**: `interfaces/api/dependencies.py`

**修改 `get_state_updater`**:
```python
def get_state_updater() -> StateUpdater:
    return StateUpdater(
        bible_repository=get_bible_repository(),
        knowledge_repository=get_knowledge_repository(),
        cast_repository=get_cast_repository(),
        indexing_service=get_indexing_service(),  # 新增
    )
```

**预期效果**:
- ✅ 生成章节后自动索引
- ✅ KnowledgePanel 的检索立即可用
- ✅ 无需手动触发索引

---

## 📋 Phase 5: 前端 API 客户端扩展（低优先级）⭐

### 目标
为新功能添加 API 客户端（可选）

### 5.1 扩展 workflow.ts

**文件**: `web-app/src/api/workflow.ts`

**添加**:
```typescript
// 获取章节状态（如果后端提供）
export const getChapterState = (novelId: string, chapterNumber: number) =>
  apiClient.get(`/novels/${novelId}/chapters/${chapterNumber}/state`)
```

### 5.2 扩展 knowledge.ts

**文件**: `web-app/src/api/knowledge.ts`

**添加**:
```typescript
// 索引管理
export const indexNovel = (novelId: string) =>
  apiClient.post(`/novels/${novelId}/index`)

export const indexChapter = (novelId: string, chapterNumber: number) =>
  apiClient.post(`/novels/${novelId}/index/chapters/${chapterNumber}`)

export const clearIndex = (novelId: string) =>
  apiClient.delete(`/novels/${novelId}/index`)
```

### 5.3 增强 KnowledgePanel（可选）

**文件**: `web-app/src/components/KnowledgePanel.vue`

**添加索引管理按钮**（在 hero 区域）:
```vue
<n-button
  v-show="sideTab === 'narrative'"
  size="small"
  quaternary
  :loading="indexing"
  @click="triggerIndex"
>
  重建索引
</n-button>
```

```typescript
const indexing = ref(false)

const triggerIndex = async () => {
  indexing.value = true
  try {
    await knowledgeApi.indexNovel(props.slug)
    message.success('索引已触发，后台处理中')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '索引失败')
  } finally {
    indexing.value = false
  }
}
```

**预期效果**:
- ✅ 用户可以手动触发索引（可选）
- ✅ 前端可以查询章节状态（如果需要）

---

## ✅ 验收标准

### 功能验收
- [ ] 生成章节后，KnowledgePanel 自动显示新的分章叙事和三元组
- [ ] 生成章节后，BiblePanel 自动显示新发现的人物
- [ ] ConsistencyReportPanel 显示真实的一致性问题（不是空的）
- [ ] KnowledgePanel 的检索功能返回相关结果
- [ ] 人物按重要性智能选择出场

### 数据验收
- [ ] test-quality-1 生成第 3 章后，Knowledge 有数据
- [ ] 提取的人物与 Bible 一致
- [ ] 关系变化被正确记录
- [ ] 一致性报告包含具体问题

### 性能验收
- [ ] StateExtractor 提取时间 < 5s
- [ ] StateUpdater 更新时间 < 2s
- [ ] 向量检索响应时间 < 100ms
- [ ] 索引单章时间 < 3s

---

## 🚀 实施顺序

### Week 1: 核心数据流
- Day 1-2: Phase 1.1 - 集成 StateExtractor
- Day 3-4: Phase 1.2 - 集成 StateUpdater
- Day 5: Phase 1.3 - 修复 ConsistencyChecker

### Week 2: 向量检索
- Day 1: Phase 2.1-2.2 - 配置环境和启动 Qdrant
- Day 2-3: Phase 2.3 - 注册服务
- Day 4: Phase 2.4 - 创建索引 API
- Day 5: Phase 2.5 - 增强检索端点

### Week 3: 智能人物管理
- Day 1-2: Phase 3.1 - 集成 CharacterIndexer
- Day 3-4: Phase 3.2 - 集成 AppearanceScheduler
- Day 5: Phase 4 - 自动索引

### Week 4: 前端优化（可选）
- Day 1-2: Phase 5 - 前端 API 客户端扩展
- Day 3-5: 端到端测试和优化

---

## 🎯 关键差异（v2 vs v1）

### v1 规划（废弃）
- ❌ 创建 6 个新前端组件
- ❌ 重新设计 UI
- ❌ 大量前端工作

### v2 规划（当前）
- ✅ 0 个新前端组件
- ✅ 只优化现有组件
- ✅ 专注后端集成
- ✅ 数据自动流入现有 UI

---

**文档版本**: v2.0
**创建日期**: 2026-04-03
**预计完成**: 2026-04-24 (3-4 周)

# Superpowers 全集成规划

**目标**: 将所有已实现但未集成的 Superpowers 功能接入生产代码，并在前端一一映射展示

**当前状态**: 代码实现 100%，集成率 23%

**目标状态**: 集成率 100%，前端完整映射

---

## 📊 集成优先级

### Phase 1: 核心数据流（最高优先级）⭐⭐⭐
**目标**: 让生成的章节能自动提取和更新数据

#### 1.1 集成 StateExtractor
- **文件**: `application/workflows/auto_novel_generation_workflow.py`
- **修改点**: `_extract_chapter_state()` 方法
- **当前**:
  ```python
  def _extract_chapter_state(self, content: str, chapter_number: int) -> ChapterState:
      # 基本实现：返回空状态
      return ChapterState(new_characters=[], ...)
  ```
- **修改为**:
  ```python
  def _extract_chapter_state(self, content: str, chapter_number: int) -> ChapterState:
      # 调用 StateExtractor
      return self.state_extractor.extract(content, chapter_number)
  ```
- **依赖注入**: 在 `__init__` 添加 `state_extractor: StateExtractor` 参数
- **dependencies.py**: 添加 `get_state_extractor()` 函数

#### 1.2 集成 StateUpdater
- **文件**: `application/workflows/auto_novel_generation_workflow.py`
- **修改点**: `generate_chapter()` 和 `generate_chapter_stream()` 方法
- **在 Phase 4 之后添加**:
  ```python
  # Phase 4: Post-Generation
  chapter_state = self._extract_chapter_state(content, chapter_number)
  consistency_report = self._check_consistency(chapter_state, novel_id)

  # Phase 4.5: Update State (新增)
  self.state_updater.update(novel_id, chapter_number, chapter_state)
  ```
- **依赖注入**: 在 `__init__` 添加 `state_updater: StateUpdater` 参数
- **dependencies.py**: 添加 `get_state_updater()` 函数

#### 1.3 修复 ConsistencyChecker 数据加载
- **文件**: `application/workflows/auto_novel_generation_workflow.py`
- **修改点**: `_check_consistency()` 方法
- **当前**: 创建空的临时对象
- **修改为**: 从仓储加载真实数据
  ```python
  def _check_consistency(self, chapter_state: ChapterState, novel_id: str) -> ConsistencyReport:
      # 从仓储加载真实数据
      bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
      character_registry = self._load_character_registry(novel_id)
      foreshadowing_registry = self.foreshadowing_repository.get_by_novel_id(NovelId(novel_id))
      # ...
      context = ConsistencyContext(bible=bible, character_registry=character_registry, ...)
      return self.consistency_checker.check_all(chapter_state, context)
  ```

**预期效果**:
- ✅ 生成章节后自动提取人物、关系、事件
- ✅ 自动更新 Bible 和 Knowledge 数据
- ✅ 一致性检查使用真实数据

---

### Phase 2: 向量检索基础设施（高优先级）⭐⭐
**目标**: 启用语义搜索和智能检索

#### 2.1 注册 EmbeddingService
- **文件**: `interfaces/api/dependencies.py`
- **添加**:
  ```python
  def get_embedding_service() -> EmbeddingService:
      api_key = os.getenv("OPENAI_API_KEY")
      if not api_key:
          logger.warning("OPENAI_API_KEY not set, embedding disabled")
          return None
      return OpenAIEmbeddingService(api_key)
  ```

#### 2.2 注册 QdrantVectorStore
- **文件**: `interfaces/api/dependencies.py`
- **修改**:
  ```python
  def get_vector_store() -> VectorStore:
      # 当前返回 None
      # 修改为返回真实的 Qdrant 实例
      qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
      embedding_service = get_embedding_service()
      if not embedding_service:
          return None
      return QdrantVectorStore(qdrant_url, embedding_service)
  ```

#### 2.3 注册 IndexingService
- **文件**: `interfaces/api/dependencies.py`
- **添加**:
  ```python
  def get_indexing_service() -> IndexingService:
      return IndexingService(
          vector_store=get_vector_store(),
          chapter_summarizer=get_chapter_summarizer(),
          chapter_repository=get_chapter_repository()
      )
  ```

#### 2.4 创建索引 API 端点
- **文件**: `interfaces/api/v1/indexing.py` (新建)
- **端点**:
  - `POST /api/v1/novels/{novel_id}/index` - 索引所有章节
  - `POST /api/v1/novels/{novel_id}/chapters/{chapter_number}/index` - 索引单章
  - `POST /api/v1/novels/{novel_id}/search` - 语义搜索
  - `DELETE /api/v1/novels/{novel_id}/index` - 清空索引

**预期效果**:
- ✅ 章节内容可以被索引到向量数据库
- ✅ 支持语义搜索相关章节
- ✅ ContextBuilder 可以使用向量检索

---

### Phase 3: 智能人物管理（中优先级）⭐
**目标**: 启用人物分层管理和智能出场调度

#### 3.1 集成 CharacterRegistry
- **文件**: `interfaces/api/dependencies.py`
- **添加**:
  ```python
  def get_character_registry(novel_id: str) -> CharacterRegistry:
      # 从 Bible 加载人物，构建 CharacterRegistry
      bible = get_bible_repository().get_by_novel_id(NovelId(novel_id))
      registry = CharacterRegistry(id=f"{novel_id}-registry", novel_id=novel_id)
      if bible:
          for char in bible.characters:
              # 根据角色定位判断重要性
              importance = _infer_importance(char)
              registry.register_character(char, importance)
      return registry
  ```

#### 3.2 集成 CharacterIndexer
- **文件**: `interfaces/api/dependencies.py`
- **添加**:
  ```python
  def get_character_indexer() -> CharacterIndexer:
      return CharacterIndexer(
          vector_store=get_vector_store(),
          embedding_service=get_embedding_service()
      )
  ```

#### 3.3 集成 AppearanceScheduler
- **文件**: `application/services/context_builder.py`
- **修改**: 在 `__init__` 添加 `appearance_scheduler: AppearanceScheduler`
- **在 `build_context` 中使用**:
  ```python
  def build_context(self, novel_id: str, chapter_number: int, outline: str, max_tokens: int = 35000) -> str:
      # 1. 调度人物出场
      scheduled_characters = self.appearance_scheduler.schedule_appearances(
          novel_id, chapter_number, outline
      )

      # 2. 构建上下文（使用调度结果）
      layer1 = self._build_layer1_core_context(...)
      layer2 = self._build_layer2_smart_retrieval(novel_id, chapter_number, outline, layer2_budget, scheduled_characters)
      ...
  ```

**预期效果**:
- ✅ 人物按重要性分层管理
- ✅ 智能选择出场人物
- ✅ 基于语义搜索相关人物

---

### Phase 4: API 端点扩展（中优先级）⭐
**目标**: 为新功能提供 HTTP 接口

#### 4.1 状态查看端点
- **文件**: `interfaces/api/v1/state.py` (新建)
- **端点**:
  - `GET /api/v1/novels/{novel_id}/state` - 获取小说当前状态
  - `GET /api/v1/novels/{novel_id}/chapters/{chapter_number}/state` - 获取章节状态
  - `GET /api/v1/novels/{novel_id}/characters` - 获取人物列表（分层）
  - `GET /api/v1/novels/{novel_id}/relationships` - 获取关系图谱

#### 4.2 人物管理端点
- **文件**: `interfaces/api/v1/characters.py` (新建)
- **端点**:
  - `GET /api/v1/novels/{novel_id}/characters/search?q=xxx` - 语义搜索人物
  - `GET /api/v1/novels/{novel_id}/characters/{char_id}/activity` - 获取人物活跃度
  - `POST /api/v1/novels/{novel_id}/characters/{char_id}/importance` - 更新重要性

#### 4.3 一致性报告端点（增强）
- **文件**: `interfaces/api/v1/generation.py`
- **修改**: `GET /api/v1/novels/{novel_id}/consistency-report` 返回真实数据

**预期效果**:
- ✅ 前端可以查询所有状态数据
- ✅ 支持人物搜索和管理
- ✅ 一致性报告可视化

---

### Phase 5: 前端映射和 UI 集成（中优先级）⭐
**目标**: 在前端展示所有新功能

#### 5.1 API 客户端
- **文件**: `web-app/src/api/state.ts` (新建)
  ```typescript
  export const stateApi = {
    getNovelState: (novelId: string) => apiClient.get(`/novels/${novelId}/state`),
    getChapterState: (novelId: string, chapterNumber: number) =>
      apiClient.get(`/novels/${novelId}/chapters/${chapterNumber}/state`),
    getCharacters: (novelId: string) => apiClient.get(`/novels/${novelId}/characters`),
    searchCharacters: (novelId: string, query: string) =>
      apiClient.get(`/novels/${novelId}/characters/search`, { params: { q: query } }),
  }
  ```

- **文件**: `web-app/src/api/indexing.ts` (新建)
  ```typescript
  export const indexingApi = {
    indexNovel: (novelId: string) => apiClient.post(`/novels/${novelId}/index`),
    indexChapter: (novelId: string, chapterNumber: number) =>
      apiClient.post(`/novels/${novelId}/chapters/${chapterNumber}/index`),
    searchChapters: (novelId: string, query: string) =>
      apiClient.post(`/novels/${novelId}/search`, { query }),
  }
  ```

#### 5.2 UI 组件映射

##### 5.2.1 章节状态面板
- **组件**: `web-app/src/components/ChapterStatePanel.vue` (新建)
- **位置**: 章节编辑页右侧栏
- **展示内容**:
  - 提取的人物列表
  - 人物行为摘要
  - 关系变化
  - 新埋伏笔 / 已回收伏笔
  - 关键事件

##### 5.2.2 一致性报告面板
- **组件**: `web-app/src/components/ConsistencyReportPanel.vue` (增强)
- **位置**: 章节生成后弹窗
- **展示内容**:
  - Issues（红色警告）
  - Warnings（黄色提示）
  - Suggestions（建议列表）
  - 一致性评分

##### 5.2.3 人物管理面板
- **组件**: `web-app/src/components/CharacterManagementPanel.vue` (新建)
- **位置**: 侧边栏新增 Tab
- **功能**:
  - 人物列表（按重要性分层）
  - 活跃度可视化
  - 语义搜索人物
  - 出场统计

##### 5.2.4 关系图谱（增强）
- **组件**: `web-app/src/components/RelationshipGraph.vue` (增强)
- **位置**: 现有关系图页面
- **新增功能**:
  - 显示关系强度（线条粗细）
  - 显示关系趋势（颜色：改善/恶化/稳定）
  - 点击节点显示人物详情
  - 显示共同联系人

##### 5.2.5 向量搜索面板
- **组件**: `web-app/src/components/SemanticSearchPanel.vue` (新建)
- **位置**: 顶部搜索栏
- **功能**:
  - 输入查询文本
  - 显示相关章节（按相似度排序）
  - 显示相关人物
  - 高亮匹配内容

##### 5.2.6 索引管理面板
- **组件**: `web-app/src/components/IndexManagementPanel.vue` (新建)
- **位置**: 设置页面
- **功能**:
  - 查看索引状态
  - 手动触发索引
  - 清空索引
  - 索引进度显示

#### 5.3 工作流集成
- **文件**: `web-app/src/components/workbench/WorkArea.vue`
- **修改**: 生成章节后自动显示状态和一致性报告
  ```typescript
  async function generateChapter() {
    await consumeGenerateChapterStream(novelId, data, {
      onDone: (result) => {
        // 显示生成的内容
        chapterContent.value = result.content

        // 显示一致性报告
        consistencyReport.value = result.consistency_report
        showConsistencyDialog.value = true

        // 刷新章节状态
        await loadChapterState(chapterNumber)
      }
    })
  }
  ```

**预期效果**:
- ✅ 所有后端功能在前端可见
- ✅ 用户可以查看提取的状态
- ✅ 用户可以管理人物和关系
- ✅ 用户可以使用语义搜索

---

## 🗂️ 文件清单

### 后端修改
1. `application/workflows/auto_novel_generation_workflow.py` - 集成 StateExtractor/StateUpdater
2. `interfaces/api/dependencies.py` - 注册所有服务
3. `interfaces/api/v1/state.py` - 新建状态查看端点
4. `interfaces/api/v1/characters.py` - 新建人物管理端点
5. `interfaces/api/v1/indexing.py` - 新建索引管理端点
6. `application/services/context_builder.py` - 集成 AppearanceScheduler

### 前端新建
1. `web-app/src/api/state.ts` - 状态 API 客户端
2. `web-app/src/api/indexing.ts` - 索引 API 客户端
3. `web-app/src/components/ChapterStatePanel.vue` - 章节状态面板
4. `web-app/src/components/ConsistencyReportPanel.vue` - 一致性报告面板（增强）
5. `web-app/src/components/CharacterManagementPanel.vue` - 人物管理面板
6. `web-app/src/components/SemanticSearchPanel.vue` - 语义搜索面板
7. `web-app/src/components/IndexManagementPanel.vue` - 索引管理面板

### 前端修改
1. `web-app/src/components/workbench/WorkArea.vue` - 集成状态显示
2. `web-app/src/components/RelationshipGraph.vue` - 增强关系图谱

---

## 📈 实施顺序

### Week 1: 核心数据流
- Day 1-2: Phase 1.1 - 集成 StateExtractor
- Day 3-4: Phase 1.2 - 集成 StateUpdater
- Day 5: Phase 1.3 - 修复 ConsistencyChecker

### Week 2: 向量检索
- Day 1-2: Phase 2.1-2.2 - 注册 Embedding 和 VectorStore
- Day 3-4: Phase 2.3-2.4 - IndexingService 和 API
- Day 5: 测试向量检索功能

### Week 3: 人物管理
- Day 1-2: Phase 3.1-3.2 - CharacterRegistry 和 Indexer
- Day 3-4: Phase 3.3 - AppearanceScheduler
- Day 5: 测试人物管理功能

### Week 4: API 和前端
- Day 1-2: Phase 4 - 创建所有 API 端点
- Day 3-5: Phase 5.1-5.2 - 前端 API 客户端和 UI 组件

### Week 5: 集成和测试
- Day 1-3: Phase 5.3 - 工作流集成
- Day 4-5: 端到端测试和优化

---

## ✅ 验收标准

### 功能验收
- [ ] 生成章节后自动提取人物、关系、事件
- [ ] 自动更新 Bible 和 Knowledge 数据
- [ ] 一致性检查使用真实数据并返回有意义的报告
- [ ] 章节可以被索引到向量数据库
- [ ] 支持语义搜索章节和人物
- [ ] 人物按重要性分层显示
- [ ] 关系图谱显示强度和趋势
- [ ] 前端所有面板正常工作

### 性能验收
- [ ] StateExtractor 提取时间 < 5s
- [ ] StateUpdater 更新时间 < 2s
- [ ] 向量检索响应时间 < 100ms
- [ ] 人物搜索响应时间 < 200ms
- [ ] 索引单章时间 < 3s

### 数据验收
- [ ] test-quality-1 生成第3章后，Knowledge 有数据
- [ ] 提取的人物与 Bible 一致
- [ ] 关系变化被正确记录
- [ ] 一致性报告包含具体问题

---

## 🚨 风险和依赖

### 外部依赖
- **Qdrant**: 需要运行 Qdrant 服务（Docker）
- **OpenAI API**: 需要 OPENAI_API_KEY（用于 Embedding）
- **Anthropic API**: 需要 ANTHROPIC_API_KEY（用于 StateExtractor）

### 技术风险
1. **StateExtractor 准确性**: LLM 提取可能不准确
   - 缓解：使用结构化 prompt，低温度，人工审核
2. **向量检索相关性**: 检索结果可能不够相关
   - 缓解：调整 Embedding 模型，优化检索参数
3. **性能瓶颈**: 大规模数据可能导致性能问题
   - 缓解：分层加载，缓存热数据，异步处理

---

## 📝 后续优化

### 短期（1-2 个月）
- [ ] 添加 Redis 缓存层
- [ ] 实现异步任务队列
- [ ] 优化向量检索性能
- [ ] 增加更多 LLM 提供商支持

### 中期（3-6 个月）
- [ ] 实现实时协作编辑
- [ ] 版本控制和回滚
- [ ] 高级分析和可视化
- [ ] 移动端适配

### 长期（6-12 个月）
- [ ] 分布式部署
- [ ] 微服务架构
- [ ] AI 模型微调
- [ ] 社区生态建设

---

**文档版本**: v1.0
**创建日期**: 2026-04-03
**预计完成**: 2026-05-03 (5 周)

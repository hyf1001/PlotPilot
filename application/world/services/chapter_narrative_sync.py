"""章节保存后：LLM 生成章末总结 → 节拍沿用既有规划 → StoryKnowledge → 向量索引。

节拍来源（按优先级，不由 LLM 现编）：
1. 知识库里该章已有 beat_sections（宏观规划 / 用户手填）
2. 结构树中该章节点 outline（规划节拍，按换行/分号拆条）
3. 仍无则保持空列表，仅写 summary。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, List, Optional, Tuple

from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel,
)
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict:
    """从模型输出中解析 JSON 对象。"""
    s = (text or "").strip()
    if not s:
        return {}
    if "```" in s:
        if "```json" in s:
            start = s.find("```json") + 7
            end = s.find("```", start)
            if end != -1:
                s = s[start:end].strip()
        else:
            start = s.find("```") + 3
            end = s.rfind("```")
            if end > start:
                s = s[start:end].strip()
    if not s.startswith("{"):
        i = s.find("{")
        if i != -1:
            s = s[i:]
    return json.loads(s)


def _beats_from_structure_outline(novel_id: str, chapter_number: int) -> List[str]:
    """从结构树章节节点的 outline 拆成节拍条（规划层本来就有）。"""
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

        repo = StoryNodeRepository(str(get_db_path()))
        nodes = repo.get_by_novel_sync(novel_id)
        for n in nodes:
            if n.node_type != NodeType.CHAPTER:
                continue
            if int(n.number) != int(chapter_number):
                continue
            outline = (n.outline or "").strip()
            if not outline:
                return []
            parts = re.split(r"[\n\r；;]+", outline)
            return [p.strip() for p in parts if p.strip()][:32]
    except Exception as e:
        logger.debug("从结构树取 outline 失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
    return []


def _resolve_beat_sections(
    novel_id: str,
    chapter_number: int,
    existing_beats: List[str],
) -> List[str]:
    """节拍：优先已有知识库条；否则用结构树 outline。"""
    cleaned = [str(b).strip() for b in (existing_beats or []) if str(b).strip()]
    if cleaned:
        return cleaned
    return _beats_from_structure_outline(novel_id, chapter_number)


async def llm_chapter_extract_bundle(
    llm: LLMService,
    chapter_content: str,
    chapter_number: int,
) -> dict:
    """一次 LLM 调用：叙事摘要 + 关键事件/埋线 + 人物关系三元组 + 伏笔线索 + 故事线进展 + 张力值 + 对话提取（避免多次调用）。"""
    body = chapter_content.strip()
    if len(body) > 24000:
        body = body[:24000] + "\n\n…（正文过长已截断）"

    system = """你是网文叙事编辑与信息抽取。根据章节正文输出**一个** JSON 对象（不要其它说明文字）：
{
  "summary": "string，200～500 字，章末叙事总结，便于检索与衔接",
  "key_events": "string",
  "open_threads": "string",
  "relation_triples": [ {"subject": "主体", "predicate": "关系", "object": "客体"} ],
  "foreshadow_hints": [ {"description": "伏笔或悬念描述"} ],
  "storyline_progress": [ {"type": "主线|支线|感情线", "description": "本章该线进展"} ],
  "tension_score": 50,
  "dialogues": [ {"speaker": "角色名", "content": "对话内容", "context": "对话场景"} ]
}
约束：
- relation_triples：只写文中明确出现的关系，最多 8 条；无则 []。
- foreshadow_hints：潜在伏笔/未解悬念，最多 4 条；无则 []。
- storyline_progress：本章推进的故事线，最多 5 条；无则 []。
- tension_score：章节张力值 0-100（冲突/悬念/情绪强度），平淡=20-40，正常=40-60，高潮=60-80，巅峰=80-100。
- dialogues：重要对话（推动剧情/展现性格），最多 10 条；无则 []。
- 不要编造 beat 列表；summary/key_events/open_threads 用中文；严格合法 JSON。"""

    user = f"第 {chapter_number} 章正文如下：\n\n{body}"

    prompt = Prompt(system=system, user=user)
    config = GenerationConfig(max_tokens=4096, temperature=0.45)

    result = await llm.generate(prompt, config)
    raw = result.content if hasattr(result, "content") else str(result)
    data = _extract_json_object(raw)

    triples_raw = data.get("relation_triples") or data.get("triples") or []
    if not isinstance(triples_raw, list):
        triples_raw = []
    hints_raw = data.get("foreshadow_hints") or data.get("foreshadows") or []
    if not isinstance(hints_raw, list):
        hints_raw = []
    storyline_raw = data.get("storyline_progress") or []
    if not isinstance(storyline_raw, list):
        storyline_raw = []
    dialogues_raw = data.get("dialogues") or []
    if not isinstance(dialogues_raw, list):
        dialogues_raw = []

    tension_score = data.get("tension_score", 50)
    try:
        tension_score = float(tension_score)
        tension_score = max(0.0, min(100.0, tension_score))
    except (ValueError, TypeError):
        tension_score = 50.0

    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_events": str(data.get("key_events", "")).strip(),
        "open_threads": str(data.get("open_threads", "")).strip(),
        "relation_triples": triples_raw[:8],
        "foreshadow_hints": hints_raw[:4],
        "storyline_progress": storyline_raw[:5],
        "tension_score": tension_score,
        "dialogues": dialogues_raw[:10],
    }


def persist_bundle_triples_and_foreshadows(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    triple_repository: Any,
    foreshadowing_repo: Any,
) -> None:
    """将 bundle 中的三元组与伏笔写入表（与旧 BG 两任务等价，但只解析一次 JSON）。"""
    triples = bundle.get("relation_triples") or []
    hints = bundle.get("foreshadow_hints") or []

    if triple_repository and triples:
        kr = getattr(triple_repository, "_kr", None)
        if kr is None:
            logger.warning("triple_repository 无 _kr，跳过三元组落库")
        else:
            for item in triples:
                if not isinstance(item, dict):
                    continue
                s = str(item.get("subject", "")).strip()
                p = str(item.get("predicate", "")).strip()
                o = str(item.get("object", "")).strip()
                if not (s and p and o):
                    continue
                row = {
                    "id": str(uuid.uuid4()),
                    "subject": s,
                    "predicate": p,
                    "object": o,
                    "chapter_number": chapter_number,
                    "source_type": "autopilot_extract",
                    "confidence": 0.7,
                    "entity_type": "character",
                    "note": "",
                }
                try:
                    kr.save_triple(novel_id, row)
                except Exception as e:
                    logger.debug("三元组落库跳过: %s", e)

    if foreshadowing_repo and hints:
        try:
            registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
            if not registry:
                return
            for h in hints:
                if not isinstance(h, dict):
                    desc = str(h).strip()
                else:
                    desc = str(h.get("description", "")).strip()
                if not desc:
                    continue
                try:
                    registry.register(
                        Foreshadowing(
                            id=str(uuid.uuid4()),
                            planted_in_chapter=max(1, chapter_number),
                            description=desc,
                            importance=ImportanceLevel.MEDIUM,
                            status=ForeshadowingStatus.PLANTED,
                        )
                    )
                except Exception:
                    pass
            foreshadowing_repo.save(registry)
        except Exception as e:
            logger.warning("伏笔落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
def _auto_generate_plot_point(
    novel_id: str,
    chapter_number: int,
    tension_score: float,
    chapter_repository: Any,
    plot_arc_repository: Any,
) -> None:
    """自动生成剧情点：当张力值显著变化时添加到情节弧。"""
    try:
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
        from domain.novel.value_objects.tension_level import TensionLevel

        # 获取前一章的张力值
        chapters = chapter_repository.list_by_novel(NovelId(novel_id))
        prev_ch = next((ch for ch in chapters if ch.number == chapter_number - 1), None)

        if not prev_ch:
            return  # 第一章不生成剧情点

        prev_tension = prev_ch.tension_score
        tension_diff = abs(tension_score - prev_tension)

        # 判断是否需要生成剧情点
        should_generate = False
        point_type = PlotPointType.RISING_ACTION
        description = ""

        # 1. 张力显著上升（>20分）
        if tension_score - prev_tension > 20:
            should_generate = True
            if tension_score >= 80:
                point_type = PlotPointType.CLIMAX
                description = f"高潮：张力从 {prev_tension:.0f} 跃升至 {tension_score:.0f}"
            elif tension_score >= 60:
                point_type = PlotPointType.TURNING_POINT
                description = f"转折：张力从 {prev_tension:.0f} 上升至 {tension_score:.0f}"
            else:
                point_type = PlotPointType.RISING_ACTION
                description = f"上升：张力从 {prev_tension:.0f} 提升至 {tension_score:.0f}"

        # 2. 张力显著下降（>20分）
        elif prev_tension - tension_score > 20:
            should_generate = True
            if prev_tension >= 70 and tension_score < 50:
                point_type = PlotPointType.FALLING_ACTION
                description = f"回落：张力从 {prev_tension:.0f} 降至 {tension_score:.0f}"
            else:
                point_type = PlotPointType.RESOLUTION
                description = f"缓和：张力从 {prev_tension:.0f} 回落至 {tension_score:.0f}"

        # 3. 达到峰值（>=85）
        elif tension_score >= 85 and prev_tension < 85:
            should_generate = True
            point_type = PlotPointType.CLIMAX
            description = f"巅峰：张力达到 {tension_score:.0f}"

        if not should_generate:
            return

        # 转换张力分数到 TensionLevel
        if tension_score >= 80:
            tension_level = TensionLevel.PEAK
        elif tension_score >= 60:
            tension_level = TensionLevel.HIGH
        elif tension_score >= 40:
            tension_level = TensionLevel.MEDIUM
        else:
            tension_level = TensionLevel.LOW

        # 获取或创建情节弧
        plot_arc = plot_arc_repository.get_by_novel_id(NovelId(novel_id))
        if not plot_arc:
            from domain.novel.entities.plot_arc import PlotArc
            plot_arc = PlotArc(
                id=str(uuid.uuid4()),
                novel_id=NovelId(novel_id),
                slug="default",
                display_name="主情节弧"
            )

        # 检查该章是否已有剧情点
        existing = any(p.chapter_number == chapter_number for p in plot_arc.key_points)
        if existing:
            return

        # 添加剧情点
        plot_point = PlotPoint(
            chapter_number=chapter_number,
            point_type=point_type,
            description=description,
            tension=tension_level
        )
        plot_arc.add_plot_point(plot_point)
        plot_arc_repository.save(plot_arc)

        logger.info("自动生成剧情点 novel=%s ch=%s type=%s tension=%.0f",
                   novel_id, chapter_number, point_type.value, tension_score)

    except Exception as e:
        logger.warning("自动生成剧情点失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _auto_advance_milestone(
    novel_id: str,
    chapter_number: int,
    storyline_progress: List[dict],
    storyline_repository: Any,
) -> None:
    """自动推进里程碑：根据进展描述判断是否达成里程碑条件。"""
    try:
        from domain.novel.value_objects.novel_id import NovelId

        storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))

        for progress_item in storyline_progress:
            if not isinstance(progress_item, dict):
                continue

            line_type = str(progress_item.get("type", "")).strip()
            description = str(progress_item.get("description", "")).strip()

            if not description:
                continue

            # 匹配故事线
            matched = None
            for sl in storylines:
                if line_type in sl.name or line_type in sl.storyline_type.value:
                    matched = sl
                    break

            if not matched or not matched.milestones:
                continue

            # 检查当前里程碑是否应该推进
            current_idx = matched.current_milestone_index
            if current_idx >= len(matched.milestones):
                continue  # 已完成所有里程碑

            current_milestone = matched.milestones[current_idx]

            # 判断是否达成里程碑（章节号在目标范围内）
            if (current_milestone.target_chapter_start <= chapter_number <=
                current_milestone.target_chapter_end):

                # 检查关键词匹配（简单实现）
                milestone_keywords = current_milestone.description.lower()
                progress_keywords = description.lower()

                # 如果进展描述包含里程碑关键词，认为达成
                keyword_match = any(
                    word in progress_keywords
                    for word in milestone_keywords.split()[:3]  # 取前3个词
                )

                if keyword_match or chapter_number >= current_milestone.target_chapter_end:
                    matched.current_milestone_index = current_idx + 1
                    storyline_repository.save(matched)
                    logger.info("自动推进里程碑 novel=%s storyline=%s milestone=%d->%d ch=%s",
                               novel_id, matched.name, current_idx, current_idx + 1, chapter_number)

    except Exception as e:
        logger.warning("自动推进里程碑失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _auto_adjust_storyline_range(
    novel_id: str,
    chapter_number: int,
    storyline_progress: List[dict],
    storyline_repository: Any,
) -> None:
    """自动调整故事线范围：检测新故事线开始或现有故事线结束。"""
    try:
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.storyline_type import StorylineType
        from domain.novel.value_objects.storyline_status import StorylineStatus
        from domain.novel.entities.storyline import Storyline

        storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))

        for progress_item in storyline_progress:
            if not isinstance(progress_item, dict):
                continue

            line_type = str(progress_item.get("type", "")).strip()
            description = str(progress_item.get("description", "")).strip()

            if not description:
                continue

            # 检测关键词判断是否是新故事线开始或结束
            is_start = any(kw in description for kw in ["开始", "启动", "引入", "出现"])
            is_end = any(kw in description for kw in ["结束", "完成", "解决", "落幕"])

            # 匹配现有故事线
            matched = None
            for sl in storylines:
                if line_type in sl.name or line_type in sl.storyline_type.value:
                    matched = sl
                    break

            if matched:
                # 更新现有故事线范围
                if is_end and matched.status != StorylineStatus.COMPLETED:
                    # 故事线结束，更新结束章节
                    if chapter_number > matched.estimated_chapter_end:
                        matched.estimated_chapter_end = chapter_number
                        matched.status = StorylineStatus.COMPLETED
                        storyline_repository.save(matched)
                        logger.info("自动结束故事线 novel=%s storyline=%s end_ch=%d",
                                   novel_id, matched.name, chapter_number)

                elif chapter_number > matched.estimated_chapter_end:
                    # 故事线超出预期范围，自动延长
                    matched.estimated_chapter_end = chapter_number + 5  # 预留5章
                    storyline_repository.save(matched)
                    logger.info("自动延长故事线 novel=%s storyline=%s new_end=%d",
                               novel_id, matched.name, matched.estimated_chapter_end)

            elif is_start:
                # 创建新故事线
                storyline_type_map = {
                    "主线": StorylineType.MAIN,
                    "支线": StorylineType.SIDE,
                    "感情线": StorylineType.ROMANCE,
                    "暗线": StorylineType.HIDDEN,
                }

                new_type = StorylineType.SIDE  # 默认支线
                for key, stype in storyline_type_map.items():
                    if key in line_type:
                        new_type = stype
                        break

                new_storyline = Storyline(
                    id=str(uuid.uuid4()),
                    novel_id=NovelId(novel_id),
                    storyline_type=new_type,
                    status=StorylineStatus.ACTIVE,
                    estimated_chapter_start=chapter_number,
                    estimated_chapter_end=chapter_number + 10,  # 预估10章
                    name=line_type,
                    description=description
                )
                storyline_repository.save(new_storyline)
                logger.info("自动创建故事线 novel=%s type=%s name=%s start_ch=%d",
                           novel_id, new_type.value, line_type, chapter_number)

    except Exception as e:
        logger.warning("自动调整故事线范围失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def persist_bundle_extras(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
    plot_arc_repository: Any = None,
    narrative_event_repository: Any = None,
) -> None:
    """将 bundle 中的故事线进展、张力值、对话写入表，并自动生成剧情点、推进里程碑、调整故事线范围。"""
    # 1. 张力值写入 chapters 表
    tension_score = bundle.get("tension_score")
    if chapter_repository and tension_score is not None:
        try:
            from domain.novel.value_objects.novel_id import NovelId
            chapters = chapter_repository.list_by_novel(NovelId(novel_id))
            target_ch = next((ch for ch in chapters if ch.number == chapter_number), None)
            if target_ch:
                # 更新章节的 tension_score 属性
                target_ch.tension_score = float(tension_score)
                chapter_repository.save(target_ch)
                logger.debug("张力值已落库 novel=%s ch=%s tension=%.1f", novel_id, chapter_number, tension_score)
        except Exception as e:
            logger.warning("张力值落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 2. 自动生成剧情点（基于张力变化）
    if chapter_repository and plot_arc_repository and tension_score is not None:
        _auto_generate_plot_point(
            novel_id, chapter_number, tension_score,
            chapter_repository, plot_arc_repository
        )

    # 3. 故事线进展更新
    storyline_progress = bundle.get("storyline_progress") or []
    if storyline_repository and storyline_progress:
        try:
            from domain.novel.value_objects.novel_id import NovelId
            storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))
            for progress_item in storyline_progress:
                if not isinstance(progress_item, dict):
                    continue
                line_type = str(progress_item.get("type", "")).strip()
                description = str(progress_item.get("description", "")).strip()
                if not description:
                    continue

                # 匹配故事线类型
                matched = None
                for sl in storylines:
                    if line_type in sl.name or line_type in sl.storyline_type.value:
                        matched = sl
                        break

                if matched:
                    matched.update_progress(chapter_number, description)
                    storyline_repository.save(matched)
                    logger.debug("故事线进展已更新 novel=%s ch=%s type=%s", novel_id, chapter_number, line_type)
        except Exception as e:
            logger.warning("故事线进展落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 4. 自动推进里程碑
    if storyline_repository and storyline_progress:
        _auto_advance_milestone(novel_id, chapter_number, storyline_progress, storyline_repository)

    # 5. 自动调整故事线范围
    if storyline_repository and storyline_progress:
        _auto_adjust_storyline_range(novel_id, chapter_number, storyline_progress, storyline_repository)

    # 6. 对话提取（写入 narrative_events 表）
    dialogues = bundle.get("dialogues") or []
    if narrative_event_repository and dialogues:
        try:
            for dialogue in dialogues:
                if not isinstance(dialogue, dict):
                    continue
                speaker = str(dialogue.get("speaker", "")).strip()
                content = str(dialogue.get("content", "")).strip()
                context = str(dialogue.get("context", "")).strip()

                if not (speaker and content):
                    continue

                # 构建事件摘要
                event_summary = f"{speaker}: {content[:100]}"
                if len(content) > 100:
                    event_summary += "..."

                # 构建 mutations（对话不涉及实体变更，可为空）
                mutations = []

                # 构建 tags
                tags = [f"对话:{speaker}"]
                if context:
                    tags.append(f"场景:{context}")

                # 写入 narrative_events
                narrative_event_repository.append_event(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    event_summary=event_summary,
                    mutations=mutations,
                    tags=tags
                )

            logger.info("对话提取完成 novel=%s ch=%s count=%d", novel_id, chapter_number, len(dialogues))
        except Exception as e:
            logger.warning("对话落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


async def sync_chapter_narrative_after_save(
    novel_id: str,
    chapter_number: int,
    content: str,
    knowledge_service: Any,
    indexing_svc: Any,
    llm_service: LLMService,
    triple_repository: Any = None,
    foreshadowing_repo: Any = None,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
    plot_arc_repository: Any = None,
    narrative_event_repository: Any = None,
) -> None:
    """异步：一次 LLM 写 summary/事件/埋线 + 可选三元组与伏笔 + 故事线/张力/对话 → 节拍来自规划 → upsert knowledge → 向量索引。"""
    if not content or not str(content).strip():
        logger.debug("跳过叙事同步：正文为空 novel=%s ch=%s", novel_id, chapter_number)
        return

    existing = None
    existing_beats: List[str] = []
    try:
        k = knowledge_service.get_knowledge(novel_id)
        for ch in getattr(k, "chapters", []) or []:
            if getattr(ch, "chapter_id", None) == chapter_number:
                existing = ch
                break
        if existing and getattr(existing, "beat_sections", None):
            existing_beats = list(existing.beat_sections or [])
    except Exception:
        pass

    try:
        bundle = await llm_chapter_extract_bundle(llm_service, content, chapter_number)
        summary = bundle.get("summary") or ""
        key_events = bundle.get("key_events") or ""
        open_threads = bundle.get("open_threads") or ""
    except Exception as e:
        logger.warning("LLM 章末 bundle 失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
        summary, key_events, open_threads = "", "", ""
        bundle = {"relation_triples": [], "foreshadow_hints": []}

    consistency_note = ""
    if existing:
        consistency_note = (existing.consistency_note or "") or ""
        if not key_events:
            key_events = existing.key_events or ""
        if not open_threads:
            open_threads = existing.open_threads or ""

    beat_sections = _resolve_beat_sections(novel_id, chapter_number, existing_beats)

    knowledge_service.upsert_chapter_summary(
        novel_id=novel_id,
        chapter_id=chapter_number,
        summary=summary,
        key_events=key_events or "（未提取）",
        open_threads=open_threads or "无",
        consistency_note=consistency_note,
        beat_sections=beat_sections,
        sync_status="synced" if summary else "draft",
    )

    if triple_repository is not None or foreshadowing_repo is not None:
        try:
            persist_bundle_triples_and_foreshadows(
                novel_id,
                chapter_number,
                bundle,
                triple_repository,
                foreshadowing_repo,
            )
        except Exception as e:
            logger.warning(
                "bundle 三元组/伏笔落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    if storyline_repository is not None or chapter_repository is not None or narrative_event_repository is not None:
        try:
            persist_bundle_extras(
                novel_id,
                chapter_number,
                bundle,
                storyline_repository,
                chapter_repository,
                plot_arc_repository,
                narrative_event_repository,
            )
        except Exception as e:
            logger.warning(
                "bundle 故事线/张力/对话落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    logger.info(
        "分章叙事已落库 novel=%s ch=%s beats=%d(src=planning/knowledge) summary_len=%d",
        novel_id,
        chapter_number,
        len(beat_sections),
        len(summary),
    )

    if indexing_svc is None:
        return
    text_for_vector = summary.strip() if summary.strip() else "；".join(beat_sections) if beat_sections else content[:800]
    try:
        await indexing_svc.ensure_collection(novel_id)
        await indexing_svc.index_chapter_summary(novel_id, chapter_number, text_for_vector)
        logger.debug("章节向量索引完成 novel=%s ch=%s", novel_id, chapter_number)
    except Exception as e:
        logger.warning("章节向量索引失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def sync_chapter_narrative_after_save_blocking(
    novel_id: str,
    chapter_number: int,
    content: str,
    knowledge_service: Any,
    indexing_svc: Any,
    llm_service: LLMService,
    triple_repository: Any = None,
    foreshadowing_repo: Any = None,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
) -> None:
    """供 FastAPI BackgroundTasks 同步入口调用。"""
    try:
        asyncio.run(
            sync_chapter_narrative_after_save(
                novel_id,
                chapter_number,
                content,
                knowledge_service,
                indexing_svc,
                llm_service,
                triple_repository=triple_repository,
                foreshadowing_repo=foreshadowing_repo,
                storyline_repository=storyline_repository,
                chapter_repository=chapter_repository,
            )
        )
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    sync_chapter_narrative_after_save(
                        novel_id,
                        chapter_number,
                        content,
                        knowledge_service,
                        indexing_svc,
                        llm_service,
                        triple_repository=triple_repository,
                        foreshadowing_repo=foreshadowing_repo,
                        storyline_repository=storyline_repository,
                        chapter_repository=chapter_repository,
                    )
                )
            finally:
                loop.close()
        else:
            raise
    except Exception as e:
        logger.warning("分章叙事同步失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

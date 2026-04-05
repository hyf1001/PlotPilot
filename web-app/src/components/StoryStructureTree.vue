<template>
  <div class="story-structure" @click="closeMenu">
    <div class="structure-body" v-if="treeData.length > 0">
      <n-tree
        :data="treeData"
        :node-props="nodeProps"
        :render-label="renderLabel"
        :render-suffix="renderSuffix"
        :selected-keys="selectedKeys"
        block-line
        expand-on-click
        selectable
        @update:selected-keys="handleSelect"
      />
    </div>

    <n-empty
      v-else-if="!loading"
      description="暂无叙事结构"
      class="structure-empty"
    >
      <template #extra>
        <n-button type="primary" @click="initializeStructure">
          AI 初始规划
        </n-button>
      </template>
    </n-empty>

    <n-spin v-if="loading" class="structure-loading" />

    <!-- 右键菜单 -->
    <n-dropdown
      trigger="manual"
      placement="bottom-start"
      :show="menuVisible"
      :options="menuOptions"
      :x="menuX"
      :y="menuY"
      @select="handleMenuSelect"
      @clickoutside="closeMenu"
    />

    <!-- 重命名对话框 -->
    <n-modal
      v-model:show="showRename"
      preset="dialog"
      title="重命名"
      positive-text="确认"
      negative-text="取消"
      @positive-click="doRename"
    >
      <n-input v-model:value="renameValue" placeholder="输入新标题" @keydown.enter="doRename" />
    </n-modal>

    <!-- 添加子节点对话框 -->
    <n-modal
      v-model:show="showAddChild"
      preset="dialog"
      :title="addChildTitle"
      positive-text="确认"
      negative-text="取消"
      @positive-click="doAddChild"
    >
      <n-input v-model:value="addChildValue" :placeholder="addChildPlaceholder" @keydown.enter="doAddChild" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, watch } from 'vue'
import { NTree, NEmpty, NSpin, NTag, NButton, NDropdown, NModal, NInput, useMessage, useDialog } from 'naive-ui'
import { structureApi, type StoryNode } from '@/api/structure'
import { workflowApi } from '@/api/workflow'

const props = defineProps<{
  slug: string
  currentChapterId?: number | null
}>()

const emit = defineEmits<{
  selectChapter: [id: number]
  planAct: [actId: string, actTitle: string]
}>()

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const treeData = ref<StoryNode[]>([])
const selectedKeys = ref<string[]>([])

// 右键菜单状态
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const menuTargetNode = ref<StoryNode | null>(null)

// 重命名状态
const showRename = ref(false)
const renameValue = ref('')

// 添加子节点状态
const showAddChild = ref(false)
const addChildValue = ref('')
const addChildTitle = computed(() => {
  const t = menuTargetNode.value?.node_type
  if (t === 'part') return '添加卷'
  if (t === 'volume') return '添加幕'
  if (t === 'act') return '添加章节'
  return '添加子节点'
})
const addChildPlaceholder = computed(() => {
  const t = menuTargetNode.value?.node_type
  if (t === 'part') return '卷标题'
  if (t === 'volume') return '幕标题'
  if (t === 'act') return '章节标题'
  return '标题'
})

// 右键菜单选项（根据节点类型动态生成）
const menuOptions = computed(() => {
  const node = menuTargetNode.value
  if (!node) return []
  const items: any[] = [
    { label: '重命名', key: 'rename' },
  ]
  if (node.node_type === 'part') {
    items.push({ label: '➕ 添加卷', key: 'add-child' })
  } else if (node.node_type === 'volume') {
    items.push({ label: '➕ 添加幕', key: 'add-child' })
  } else if (node.node_type === 'act') {
    items.push({ label: '➕ 添加章节（手动）', key: 'add-child' })
    items.push({ type: 'divider', key: 'div' })
    items.push({ label: '🤖 AI 规划章节', key: 'plan-act' })
  }
  items.push({ type: 'divider', key: 'div-del' })
  items.push({ label: '🗑 删除', key: 'delete' })
  return items
})

watch(() => props.currentChapterId, (chapterId) => {
  if (chapterId) {
    selectedKeys.value = [`chapter-${props.slug}-chapter-${chapterId}`]
  } else {
    selectedKeys.value = []
  }
}, { immediate: true })

const convertToTreeNode = (node: StoryNode): any => {
  const iconMap: Record<string, string> = {
    part: '📚',
    volume: '📖',
    act: '🎬',
    chapter: '📄',
  }
  return {
    key: node.id,
    label: node.title,
    ...node,
    icon: iconMap[node.node_type] || '📄',
    display_name: node.title,
    children: node.children?.map(convertToTreeNode) || [],
  }
}

const loadTree = async () => {
  loading.value = true
  try {
    const res = await structureApi.getTree(props.slug)
    const nodes = res.tree?.nodes || []
    treeData.value = nodes.length > 0 ? nodes.map(convertToTreeNode) : []
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载结构失败')
  } finally {
    loading.value = false
  }
}

const initializeStructure = async () => {
  dialog.warning({
    title: 'AI 初始规划',
    content: '将使用 AI 生成初始 Bible（世界设定）和章节大纲。此操作可能需要 1-2 分钟，确认继续？',
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: () => {
      loading.value = true
      void (async () => {
        try {
          const res = await workflowApi.planNovel(props.slug, 'initial', false)
          if (res.success) {
            message.success('规划完成，正在加载叙事结构...')
            await loadTree()
          } else {
            message.warning(res.message || '规划失败')
          }
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '规划失败')
        } finally {
          loading.value = false
        }
      })()
      return true
    },
  })
}

const handleSelect = (keys: string[]) => {
  if (!keys.length) return
  const findNode = (nodes: StoryNode[], id: string): StoryNode | null => {
    for (const node of nodes) {
      if (node.id === id) return node
      if (node.children) {
        const found = findNode(node.children, id)
        if (found) return found
      }
    }
    return null
  }
  const node = findNode(treeData.value, keys[0])
  if (node?.node_type === 'chapter') {
    const match = node.id.match(/chapter-(\d+)$/)
    if (match) emit('selectChapter', parseInt(match[1]))
  }
}

// 右键菜单
const handleContextMenu = (e: MouseEvent, node: StoryNode) => {
  e.preventDefault()
  e.stopPropagation()
  menuTargetNode.value = node
  menuX.value = e.clientX
  menuY.value = e.clientY
  menuVisible.value = true
}

const closeMenu = () => { menuVisible.value = false }

const handleMenuSelect = (key: string) => {
  closeMenu()
  const node = menuTargetNode.value
  if (!node) return
  if (key === 'rename') {
    renameValue.value = node.title
    showRename.value = true
  } else if (key === 'add-child') {
    addChildValue.value = ''
    showAddChild.value = true
  } else if (key === 'plan-act') {
    emit('planAct', node.id, node.title)
  } else if (key === 'delete') {
    dialog.warning({
      title: '确认删除',
      content: `删除「${node.title}」及其所有子节点？此操作不可恢复。`,
      positiveText: '删除',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          await structureApi.deleteNode(props.slug, node.id)
          message.success('已删除')
          await loadTree()
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '删除失败')
        }
      },
    })
  }
}

const doRename = async () => {
  const node = menuTargetNode.value
  if (!node || !renameValue.value.trim()) return
  showRename.value = false
  try {
    await structureApi.updateNode(props.slug, node.id, { title: renameValue.value.trim() })
    message.success('已重命名')
    await loadTree()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重命名失败')
  }
}

const childTypeMap: Record<string, string> = {
  part: 'volume',
  volume: 'act',
  act: 'chapter',
}

const doAddChild = async () => {
  const node = menuTargetNode.value
  if (!node || !addChildValue.value.trim()) return
  showAddChild.value = false
  const childType = childTypeMap[node.node_type]
  if (!childType) return
  try {
    await structureApi.createNode(props.slug, {
      node_type: childType as any,
      parent_id: node.id,
      title: addChildValue.value.trim(),
      number: 1,
    })
    message.success('已添加')
    await loadTree()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '添加失败')
  }
}

// 渲染节点标签
const renderLabel = ({ option }: { option: StoryNode }) => {
  const elements: any[] = [
    h('span', { class: 'node-icon' }, option.icon),
    h('span', { class: 'node-title' }, option.display_name),
  ]
  if (option.node_type === 'chapter') {
    const hasContent = option.word_count && option.word_count > 0
    elements.push(
      h(NTag, {
        size: 'small',
        type: hasContent ? 'success' : 'default',
        round: true,
        style: { marginLeft: '8px' },
      }, () => hasContent ? '已收稿' : '未收稿')
    )
  }
  return h('span', { class: 'node-label' }, elements)
}

// 渲染节点后缀
const renderSuffix = ({ option }: { option: StoryNode }) => {
  const elements: any[] = []
  if (option.description && ['part', 'volume', 'act'].includes(option.node_type)) {
    elements.push(
      h('span', {
        class: 'node-description',
        style: { color: '#999', fontSize: '12px', marginLeft: '8px' },
      }, option.description)
    )
  }
  if (option.node_type === 'chapter' && option.word_count) {
    elements.push(h('span', { class: 'node-range' }, `${option.word_count}字`))
  }
  if (option.chapter_start && option.chapter_end) {
    elements.push(
      h('span', { class: 'node-range' }, `${option.chapter_start}-${option.chapter_end}章 (${option.chapter_count})`)
    )
  }
  return elements.length > 0 ? h('span', {}, elements) : null
}

// 节点属性（右键绑定）
const nodeProps = ({ option }: { option: StoryNode }) => ({
  class: `node-level-${option.level}`,
  onContextmenu: (e: MouseEvent) => handleContextMenu(e, option),
})

onMounted(() => { loadTree() })

defineExpose({ loadTree })
</script>

<style scoped>
.story-structure {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}
.structure-body {
  flex: 1;
  overflow: auto;
}
.structure-empty {
  padding: 40px 0;
}
.structure-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
.node-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-icon { font-size: 16px; }
.node-title { font-size: 13px; }
.node-range {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
}
.node-level-1 { font-weight: 600; }
.node-level-2 { font-weight: 500; }
.node-level-3 { font-weight: normal; }
.node-level-4 { font-weight: normal; font-size: 13px; }
</style>

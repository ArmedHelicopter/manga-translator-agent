"""Internationalization module for Manga Translate Agent Web UI."""

from __future__ import annotations

from enum import Enum
from typing import Callable


class Locale(str, Enum):
    """Supported locales."""
    EN = "en"
    ZH = "zh"


# Translation dictionaries
_TRANSLATIONS: dict[Locale, dict[str, str]] = {
    Locale.EN: {
        # App title
        "app_title": "Manga Translate Agent",
        "app_subtitle": "AI-Powered Manga Translation",

        # Navigation
        "nav_translate": "Translate",
        "nav_memory": "Memory",
        "nav_profiles": "Profiles",
        "nav_terms": "Terms",
        "nav_distill": "Distill",
        "nav_settings": "Settings",
        "nav_dashboard": "Dashboard",
        "nav_docs": "Documentation",

        # Tutorial steps
        "tutorial_welcome": "Welcome to Manga Translate Agent",
        "tutorial_welcome_desc": "Let's set up your translation environment in a few simple steps.",
        "tutorial_step1_title": "Configure API Provider",
        "tutorial_step1_desc": "Select your preferred AI provider for translation. We recommend OpenAI GPT-4o for best quality.",
        "tutorial_step2_title": "Source & Target Language",
        "tutorial_step2_desc": "Configure the source language (original) and target language (translation output).",
        "tutorial_step3_title": "Select Input Files",
        "tutorial_step3_desc": "Choose the manga files or directory you want to translate.",
        "tutorial_step4_title": "Start Translation",
        "tutorial_step4_desc": "Everything is ready! Start translating your manga content.",

        # Tutorial navigation
        "tutorial_next": "Next",
        "tutorial_back": "Back",
        "tutorial_skip": "Skip Tutorial",
        "tutorial_done": "Get Started",
        "tutorial_step": "Step {current} of {total}",

        # Dashboard
        "dashboard_title": "Dashboard",
        "dashboard_recent_projects": "Recent Projects",
        "dashboard_stats": "Statistics",
        "dashboard_quick_actions": "Quick Actions",
        "dashboard_total_projects": "Total Projects",
        "dashboard_total_characters": "Characters",
        "dashboard_total_terms": "Terms",
        "dashboard_total_pages": "Pages Translated",

        # Translation
        "translate_title": "Translate",
        "translate_single": "Single File",
        "translate_batch": "Batch Translation",
        "translate_select_input": "Select Input",
        "translate_output_dir": "Output Directory",
        "translate_source_lang": "Source Language",
        "translate_target_lang": "Target Language",
        "translate_provider": "AI Provider",
        "translate_start": "Start Translation",
        "translate_progress": "Translation Progress",
        "translate_status": "Status",
        "translate_completed": "Completed",
        "translate_pending": "Pending",
        "translate_failed": "Failed",

        # Memory
        "memory_title": "Memory Management",
        "memory_characters": "Characters",
        "memory_scenes": "Scenes",
        "memory_context": "Context",
        "memory_add_character": "Add Character",
        "memory_edit_character": "Edit Character",
        "memory_delete_character": "Delete Character",
        "memory_character_name_jp": "Japanese Name",
        "memory_character_name_zh": "Chinese Name",
        "memory_character_archetype": "Archetype",
        "memory_character_speech": "Speech Patterns",
        "memory_character_notes": "Translation Notes",

        # Profiles
        "profiles_title": "Character Profiles",
        "profiles_load": "Load Profile",
        "profiles_save": "Save Profile",
        "profiles_export": "Export Profiles",
        "profiles_import": "Import Profiles",
        "profiles_apply": "Apply to Translation",

        # Terms
        "terms_title": "Terminology",
        "terms_add": "Add Term",
        "terms_edit": "Edit Term",
        "terms_delete": "Delete Term",
        "terms_source": "Source Term",
        "terms_translation": "Translation",
        "terms_category": "Category",
        "terms_strategy": "Strategy",
        "terms_frequency": "Frequency",

        # Distillation
        "distill_title": "Distillation Export",
        "distill_select_source": "Select Source Directory",
        "distill_output": "Output Format",
        "distill_start": "Start Export",
        "distill_progress": "Export Progress",

        # Settings
        "settings_title": "Settings",
        "settings_general": "General",
        "settings_provider": "Provider Configuration",
        "settings_language": "Language",
        "settings_theme": "Theme",
        "settings_about": "About",
        "settings_save": "Save Settings",
        "settings_reset": "Reset to Default",

        # Provider config
        "provider_vision": "Vision Stage",
        "provider_translation": "Translation Stage",
        "provider_qa": "QA Stage",
        "provider_primary": "Primary",
        "provider_fallback": "Fallback",
        "provider_local": "Local",
        "provider_api_key": "API Key",
        "provider_model": "Model",

        # Common
        "save": "Save",
        "cancel": "Cancel",
        "delete": "Delete",
        "edit": "Edit",
        "create": "Create",
        "search": "Search",
        "filter": "Filter",
        "refresh": "Refresh",
        "loading": "Loading...",
        "no_data": "No data available",
        "confirm_delete": "Are you sure you want to delete?",
        "success": "Success",
        "error": "Error",
        "warning": "Warning",
        "info": "Info",

        # Projects
        "projects_title": "Projects",
        "projects_new": "New Project",
        "projects_open": "Open Project",
        "projects_delete": "Delete Project",
        "projects_name": "Project Name",
        "projects_created": "Created",
        "projects_updated": "Last Updated",

        # File types
        "file_pdf": "PDF",
        "file_epub": "EPUB",
        "file_cbz": "CBZ",
        "file_images": "Images",
        "file_directory": "Directory",
    },
    Locale.ZH: {
        # App title
        "app_title": "漫画翻译助手",
        "app_subtitle": "AI驱动的漫画翻译",

        # Navigation
        "nav_translate": "翻译",
        "nav_memory": "记忆",
        "nav_profiles": "角色",
        "nav_terms": "术语",
        "nav_distill": "蒸馏",
        "nav_settings": "设置",
        "nav_dashboard": "仪表盘",
        "nav_docs": "文档",

        # Tutorial steps
        "tutorial_welcome": "欢迎使用漫画翻译助手",
        "tutorial_welcome_desc": "让我们通过几个简单的步骤来设置您的翻译环境。",
        "tutorial_step1_title": "配置API提供商",
        "tutorial_step1_desc": "选择您首选的AI翻译提供商。我们推荐使用OpenAI GPT-4o以获得最佳质量。",
        "tutorial_step2_title": "源语言和目标语言",
        "tutorial_step2_desc": "配置源语言（原始语言）和目标语言（翻译输出）。",
        "tutorial_step3_title": "选择输入文件",
        "tutorial_step3_desc": "选择您想要翻译的漫画文件或目录。",
        "tutorial_step4_title": "开始翻译",
        "tutorial_step4_desc": "一切准备就绪！开始翻译您的漫画内容。",

        # Tutorial navigation
        "tutorial_next": "下一步",
        "tutorial_back": "返回",
        "tutorial_skip": "跳过教程",
        "tutorial_done": "开始使用",
        "tutorial_step": "第 {current} 步，共 {total} 步",

        # Dashboard
        "dashboard_title": "仪表盘",
        "dashboard_recent_projects": "最近项目",
        "dashboard_stats": "统计信息",
        "dashboard_quick_actions": "快捷操作",
        "dashboard_total_projects": "项目总数",
        "dashboard_total_characters": "角色数",
        "dashboard_total_terms": "术语数",
        "dashboard_total_pages": "已翻译页数",

        # Translation
        "translate_title": "翻译",
        "translate_single": "单文件翻译",
        "translate_batch": "批量翻译",
        "translate_select_input": "选择输入",
        "translate_output_dir": "输出目录",
        "translate_source_lang": "源语言",
        "translate_target_lang": "目标语言",
        "translate_provider": "AI提供商",
        "translate_start": "开始翻译",
        "translate_progress": "翻译进度",
        "translate_status": "状态",
        "translate_completed": "已完成",
        "translate_pending": "等待中",
        "translate_failed": "失败",

        # Memory
        "memory_title": "记忆管理",
        "memory_characters": "角色",
        "memory_scenes": "场景",
        "memory_context": "上下文",
        "memory_add_character": "添加角色",
        "memory_edit_character": "编辑角色",
        "memory_delete_character": "删除角色",
        "memory_character_name_jp": "日文名",
        "memory_character_name_zh": "中文名",
        "memory_character_archetype": "角色类型",
        "memory_character_speech": "说话方式",
        "memory_character_notes": "翻译备注",

        # Profiles
        "profiles_title": "角色档案",
        "profiles_load": "加载档案",
        "profiles_save": "保存档案",
        "profiles_export": "导出档案",
        "profiles_import": "导入档案",
        "profiles_apply": "应用到翻译",

        # Terms
        "terms_title": "术语表",
        "terms_add": "添加术语",
        "terms_edit": "编辑术语",
        "terms_delete": "删除术语",
        "terms_source": "源术语",
        "terms_translation": "翻译",
        "terms_category": "类别",
        "terms_strategy": "策略",
        "terms_frequency": "频率",

        # Distillation
        "distill_title": "蒸馏导出",
        "distill_select_source": "选择源目录",
        "distill_output": "输出格式",
        "distill_start": "开始导出",
        "distill_progress": "导出进度",

        # Settings
        "settings_title": "设置",
        "settings_general": "常规",
        "settings_provider": "提供商配置",
        "settings_language": "语言",
        "settings_theme": "主题",
        "settings_about": "关于",
        "settings_save": "保存设置",
        "settings_reset": "重置为默认",

        # Provider config
        "provider_vision": "视觉阶段",
        "provider_translation": "翻译阶段",
        "provider_qa": "质检阶段",
        "provider_primary": "主要",
        "provider_fallback": "备用",
        "provider_local": "本地",
        "provider_api_key": "API密钥",
        "provider_model": "模型",

        # Common
        "save": "保存",
        "cancel": "取消",
        "delete": "删除",
        "edit": "编辑",
        "create": "创建",
        "search": "搜索",
        "filter": "筛选",
        "refresh": "刷新",
        "loading": "加载中...",
        "no_data": "暂无数据",
        "confirm_delete": "确定要删除吗？",
        "success": "成功",
        "error": "错误",
        "warning": "警告",
        "info": "信息",

        # Projects
        "projects_title": "项目",
        "projects_new": "新建项目",
        "projects_open": "打开项目",
        "projects_delete": "删除项目",
        "projects_name": "项目名称",
        "projects_created": "创建时间",
        "projects_updated": "最后更新",

        # File types
        "file_pdf": "PDF",
        "file_epub": "EPUB",
        "file_cbz": "CBZ",
        "file_images": "图片",
        "file_directory": "目录",
    },
}


def get_translation(locale: Locale, key: str, **kwargs: str) -> str:
    """Get translated string with variable substitution."""
    text = _TRANSLATIONS.get(locale, _TRANSLATIONS[Locale.EN]).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def t(locale: Locale, key: str) -> Callable[[], str]:
    """Create a translation function for a specific locale and key."""
    return lambda: get_translation(locale, key)


# Supported language pairs
LANGUAGE_PAIRS = [
    ("ja", "zh-CN", "Japanese → Chinese (中文)"),
    ("ja", "en", "Japanese → English"),
    ("ko", "zh-CN", "Korean → Chinese (中文)"),
    ("ko", "en", "Korean → English"),
    ("zh-CN", "en", "Chinese → English"),
    ("en", "ja", "English → Japanese"),
    ("en", "zh-CN", "English → Chinese"),
]

# Supported file formats
SUPPORTED_FORMATS = [
    ("images", "Images Directory"),
    ("pdf", "PDF Document"),
    ("epub", "EPUB E-book"),
    ("cbz", "CBZ Comic Archive"),
    ("cbr", "CBR Comic Archive"),
]

# Provider options
PROVIDER_OPTIONS = [
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "openrouter",
    "ollama",
    "vllm",
    "lmstudio",
]
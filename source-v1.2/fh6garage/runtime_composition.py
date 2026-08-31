from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .v1_3_ui_patch import apply_v1_3_ui_patches
from .v1_3_1_patch import apply_v1_3_1_patches
from .v1_3_2_patch import apply_v1_3_2_patches
from .v1_3_2_safety_patch import apply_v1_3_2_safety_patches
from .v1_3_2_startup_patch import apply_v1_3_2_startup_patches
from .v1_3_2_list_fix import apply_v1_3_2_list_fixes
from .v1_3_2_visibility_patch import apply_v1_3_2_visibility_patches
from .v1_3_2_ui_cleanup_patch import apply_v1_3_2_ui_cleanup_patch
from .v1_3_2_ui_followup_patch import apply_v1_3_2_ui_followup_patch
from .v1_3_2_manifest_registry_patch import apply_v1_3_2_manifest_registry_patch
from .v1_3_2_card_alignment_patch import apply_v1_3_2_card_alignment_patch
from .v1_3_2_ui_performance_patch import apply_v1_3_2_ui_performance_patches
from .v1_3_2_global_ui_patch import apply_v1_3_2_global_ui_patch
from .v1_3_2_icon_overlay_fix import apply_v1_3_2_icon_overlay_fix
from .v1_3_2_compact_card_layout_patch import apply_v1_3_2_compact_card_layout_patch
from .v1_3_2_responsiveness_sort_patch import apply_v1_3_2_responsiveness_sort_patch
from .v1_3_2_responsive_columns_fix import apply_v1_3_2_responsive_columns_fix
from .v1_3_2_refresh_diff_patch import apply_v1_3_2_refresh_diff_patch
from .v1_3_2_change_view_alias_patch import apply_v1_3_2_change_view_alias_patch
from .v1_3_2_change_view_alias_sync_patch import apply_v1_3_2_change_view_alias_sync_patch
from .v1_3_2_release_layout_patch import apply_v1_3_2_release_layout_patch
from .v1_3_2_change_dialog_folder_patch import apply_v1_3_2_change_dialog_folder_patch
from .v1_3_2_change_dialog_runtime_fix import apply_v1_3_2_change_dialog_runtime_fix
from .v1_3_2_change_dialog_responsive_ui_fix import apply_v1_3_2_change_dialog_responsive_ui_fix
from .v1_3_2_auction_unapplied_recent_frame_fix import apply_v1_3_2_auction_unapplied_recent_frame_fix
from .v1_3_2_alias_manager_change_card_fix import apply_v1_3_2_alias_manager_change_card_fix
from .v1_3_2_memory_state_patch import apply_v1_3_2_memory_state_patch
from .v1_3_2_memory_filter_coordination_patch import apply_v1_3_2_memory_filter_coordination_patch
from .v1_3_2_memory_thread_safety_patch import apply_v1_3_2_memory_thread_safety_patch
from .v1_3_2_filter_alias_quality_patch import apply_v1_3_2_filter_alias_quality_patch
from .v1_3_2_dashboard_change_group_patch import apply_v1_3_2_dashboard_change_group_patch
from .v1_3_3_beta_identity_patch import apply_v1_3_3_beta_identity_patch
from .v1_3_4_card_action_layout_patch import apply_v1_3_4_card_action_layout_patch
from .v1_3_4_card_features_patch import apply_v1_3_4_card_features_patch
from .v1_3_4_metadata_toggle_icon_patch import apply_v1_3_4_metadata_toggle_icon_patch
from .v1_3_4_backup_export_patch import apply_v1_3_4_backup_export_patch
from .v1_3_4_backup_export_thread_fix_patch import apply_v1_3_4_backup_export_thread_fix_patch
from .v1_3_4_backup_export_performance_ui_patch import apply_v1_3_4_backup_export_performance_ui_patch
from .v1_3_4_backup_import_refinement_patch import apply_v1_3_4_backup_import_refinement_patch
from .v1_3_4_backup_toolbar_followup_patch import apply_v1_3_4_backup_toolbar_followup_patch
from .v1_3_4_backup_lazy_load_patch import apply_v1_3_4_backup_lazy_load_patch
from .v1_3_4_backup_lazy_watch_patch import apply_v1_3_4_backup_lazy_watch_patch
from .v1_3_4_backup_lazy_thread_bridge_patch import apply_v1_3_4_backup_lazy_thread_bridge_patch
from .v1_3_4_backup_loading_resilience_patch import apply_v1_3_4_backup_loading_resilience_patch
from .v1_3_4_backup_visual_stability_patch import apply_v1_3_4_backup_visual_stability_patch
from .v1_3_4_card_polish_export_delete_patch import apply_v1_3_4_card_polish_export_delete_patch
from .v1_3_4_livery_backup_filter_patch import apply_v1_3_4_livery_backup_filter_patch
from .v1_3_4_status_backup_label_patch import apply_v1_3_4_status_backup_label_patch
from .v1_3_4_performance_probe_patch import apply_v1_3_4_performance_probe_patch
from .v1_4_backup_repository_patch import apply_v1_4_backup_repository_patch
from .v1_4_backup_repository_followup_patch import apply_v1_4_backup_repository_followup_patch
from .v1_4_backup_watch_stability_patch import apply_v1_4_backup_watch_stability_patch
from .v1_4_local_app_data_patch import apply_v1_4_local_app_data_patch
from .v1_4_identity_patch import apply_v1_4_identity_patch
from .v1_4_ui_completion_patch import apply_v1_4_ui_completion_patch
from .v1_4_display_row_geometry_patch import apply_v1_4_display_row_geometry_patch
from .v1_4_acquisition_ui_patch import apply_v1_4_acquisition_ui_patch
from .v1_4_vehicle_data_source_patch import apply_v1_4_vehicle_data_source_patch
from .v1_4_vehicle_runtime_update_patch import apply_v1_4_vehicle_runtime_update_patch
from .v1_4_vehicle_update_finish_ui_patch import apply_v1_4_vehicle_update_finish_ui_patch
from .v1_4_vehicle_update_thread_bridge_patch import apply_v1_4_vehicle_update_thread_bridge_patch
from .v1_4_interaction_render_completion_patch import apply_v1_4_interaction_render_completion_patch
from .v1_4_right_control_width_patch import apply_v1_4_right_control_width_patch
from .v1_3_4_backup_action_wording_patch import apply_v1_3_4_backup_action_wording_patch
from .v1_3_2_thread_affinity_patch import apply_v1_3_2_thread_affinity_fix


@dataclass(frozen=True)
class RuntimePatchStep:
    name: str
    apply: Callable[..., None]
    uses_main_window: bool = True


# Single runtime composition root. The execution order below intentionally
# mirrors the previously verified app.py + backup_action_wording transitive chain.
# Do not reorder casually: legacy patches wrap/replace earlier behavior, and
# thread_affinity_fix must remain the final MainWindow mutation.
RUNTIME_PATCH_SEQUENCE: tuple[RuntimePatchStep, ...] = (
    RuntimePatchStep("v1_3_ui", apply_v1_3_ui_patches, True),
    RuntimePatchStep("v1_3_1", apply_v1_3_1_patches, True),
    RuntimePatchStep("v1_3_2", apply_v1_3_2_patches, True),
    RuntimePatchStep("v1_3_2_safety", apply_v1_3_2_safety_patches, True),
    RuntimePatchStep("v1_3_2_startup", apply_v1_3_2_startup_patches, False),
    RuntimePatchStep("v1_3_2_list_fix", apply_v1_3_2_list_fixes, True),
    RuntimePatchStep("v1_3_2_visibility", apply_v1_3_2_visibility_patches, True),
    RuntimePatchStep("v1_3_2_ui_cleanup", apply_v1_3_2_ui_cleanup_patch, True),
    RuntimePatchStep("v1_3_2_ui_followup", apply_v1_3_2_ui_followup_patch, True),
    RuntimePatchStep("v1_3_2_manifest_registry", apply_v1_3_2_manifest_registry_patch, True),
    RuntimePatchStep("v1_3_2_card_alignment", apply_v1_3_2_card_alignment_patch, True),
    RuntimePatchStep("v1_3_2_ui_performance", apply_v1_3_2_ui_performance_patches, True),
    RuntimePatchStep("v1_3_2_global_ui", apply_v1_3_2_global_ui_patch, True),
    RuntimePatchStep("v1_3_2_icon_overlay", apply_v1_3_2_icon_overlay_fix, True),
    RuntimePatchStep("v1_3_2_compact_card_layout", apply_v1_3_2_compact_card_layout_patch, True),
    RuntimePatchStep("v1_3_2_responsiveness_sort", apply_v1_3_2_responsiveness_sort_patch, True),
    RuntimePatchStep("v1_3_2_responsive_columns", apply_v1_3_2_responsive_columns_fix, True),
    RuntimePatchStep("v1_3_2_refresh_diff", apply_v1_3_2_refresh_diff_patch, True),
    RuntimePatchStep("v1_3_2_change_view_alias", apply_v1_3_2_change_view_alias_patch, True),
    RuntimePatchStep("v1_3_2_change_view_alias_sync", apply_v1_3_2_change_view_alias_sync_patch, True),
    RuntimePatchStep("v1_3_2_release_layout", apply_v1_3_2_release_layout_patch, True),
    RuntimePatchStep("v1_3_2_change_dialog_folder", apply_v1_3_2_change_dialog_folder_patch, True),
    RuntimePatchStep("v1_3_2_change_dialog_runtime", apply_v1_3_2_change_dialog_runtime_fix, True),
    RuntimePatchStep("v1_3_2_change_dialog_responsive_ui", apply_v1_3_2_change_dialog_responsive_ui_fix, True),
    RuntimePatchStep("v1_3_2_auction_unapplied_recent_frame", apply_v1_3_2_auction_unapplied_recent_frame_fix, True),
    RuntimePatchStep("v1_3_2_alias_manager_change_card", apply_v1_3_2_alias_manager_change_card_fix, True),
    RuntimePatchStep("v1_3_2_memory_state", apply_v1_3_2_memory_state_patch, True),
    RuntimePatchStep("v1_3_2_memory_filter_coordination", apply_v1_3_2_memory_filter_coordination_patch, True),
    RuntimePatchStep("v1_3_2_memory_thread_safety", apply_v1_3_2_memory_thread_safety_patch, True),
    RuntimePatchStep("v1_3_2_filter_alias_quality", apply_v1_3_2_filter_alias_quality_patch, True),
    RuntimePatchStep("v1_3_2_dashboard_change_group", apply_v1_3_2_dashboard_change_group_patch, True),
    RuntimePatchStep("v1_3_3_beta_identity", apply_v1_3_3_beta_identity_patch, True),
    RuntimePatchStep("v1_3_4_card_action_layout", apply_v1_3_4_card_action_layout_patch, True),
    RuntimePatchStep("v1_3_4_card_features", apply_v1_3_4_card_features_patch, True),
    RuntimePatchStep("v1_3_4_metadata_toggle_icon", apply_v1_3_4_metadata_toggle_icon_patch, True),
    RuntimePatchStep("v1_3_4_backup_export", apply_v1_3_4_backup_export_patch, True),
    RuntimePatchStep("v1_3_4_backup_export_thread_fix", apply_v1_3_4_backup_export_thread_fix_patch, True),
    RuntimePatchStep("v1_3_4_backup_export_performance_ui", apply_v1_3_4_backup_export_performance_ui_patch, True),
    RuntimePatchStep("v1_3_4_backup_action_wording", apply_v1_3_4_backup_action_wording_patch, True),
    RuntimePatchStep("v1_3_4_backup_import_refinement", apply_v1_3_4_backup_import_refinement_patch, True),
    RuntimePatchStep("v1_3_4_backup_toolbar_followup", apply_v1_3_4_backup_toolbar_followup_patch, True),
    RuntimePatchStep("v1_3_4_backup_lazy_load", apply_v1_3_4_backup_lazy_load_patch, True),
    RuntimePatchStep("v1_3_4_backup_lazy_watch", apply_v1_3_4_backup_lazy_watch_patch, True),
    RuntimePatchStep("v1_3_4_backup_lazy_thread_bridge", apply_v1_3_4_backup_lazy_thread_bridge_patch, True),
    RuntimePatchStep("v1_3_4_backup_loading_resilience", apply_v1_3_4_backup_loading_resilience_patch, True),
    RuntimePatchStep("v1_3_4_backup_visual_stability", apply_v1_3_4_backup_visual_stability_patch, True),
    RuntimePatchStep("v1_3_4_card_polish_export_delete", apply_v1_3_4_card_polish_export_delete_patch, True),
    RuntimePatchStep("v1_3_4_livery_backup_filter", apply_v1_3_4_livery_backup_filter_patch, True),
    RuntimePatchStep("v1_3_4_status_backup_label", apply_v1_3_4_status_backup_label_patch, True),
    RuntimePatchStep("v1_4_backup_repository", apply_v1_4_backup_repository_patch, True),
    RuntimePatchStep("v1_4_backup_repository_followup", apply_v1_4_backup_repository_followup_patch, True),
    RuntimePatchStep("v1_4_backup_watch_stability", apply_v1_4_backup_watch_stability_patch, True),
    RuntimePatchStep("v1_4_local_app_data", apply_v1_4_local_app_data_patch, True),
    RuntimePatchStep("v1_4_identity", apply_v1_4_identity_patch, True),
    RuntimePatchStep("v1_4_ui_completion", apply_v1_4_ui_completion_patch, True),
    RuntimePatchStep("v1_4_display_row_geometry", apply_v1_4_display_row_geometry_patch, True),
    RuntimePatchStep("v1_4_acquisition_ui", apply_v1_4_acquisition_ui_patch, True),
    RuntimePatchStep("v1_4_vehicle_data_source", apply_v1_4_vehicle_data_source_patch, True),
    RuntimePatchStep("v1_4_vehicle_runtime_update", apply_v1_4_vehicle_runtime_update_patch, True),
    RuntimePatchStep("v1_4_vehicle_update_finish_ui", apply_v1_4_vehicle_update_finish_ui_patch, True),
    RuntimePatchStep("v1_4_vehicle_update_thread_bridge", apply_v1_4_vehicle_update_thread_bridge_patch, True),
    RuntimePatchStep("v1_4_interaction_render_completion", apply_v1_4_interaction_render_completion_patch, True),
    RuntimePatchStep("v1_4_right_control_width", apply_v1_4_right_control_width_patch, True),
    RuntimePatchStep("v1_3_4_performance_probe", apply_v1_3_4_performance_probe_patch, True),
    RuntimePatchStep("v1_3_2_thread_affinity_fix", apply_v1_3_2_thread_affinity_fix, True),
)


def runtime_patch_names() -> tuple[str, ...]:
    return tuple(step.name for step in RUNTIME_PATCH_SEQUENCE)


def apply_runtime_patches(MainWindow: Any) -> None:
    names = runtime_patch_names()
    if len(names) != len(set(names)):
        raise RuntimeError("Runtime patch registry contains duplicate step names.")
    if not names or names[-1] != "v1_3_2_thread_affinity_fix":
        raise RuntimeError("Thread-affinity fix must remain the final runtime patch.")

    for step in RUNTIME_PATCH_SEQUENCE:
        if step.uses_main_window:
            step.apply(MainWindow)
        else:
            step.apply()

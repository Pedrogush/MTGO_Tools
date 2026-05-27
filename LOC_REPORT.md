# Lines of Code by File (.py only)

- Commit: `6acfd38` (6acfd384f55a6644e014dfea3cf12b2f43ec93b4)
- Commit date: 2026-05-27T16:06:57-03:00
- Generated (UTC): 2026-05-27 19:57:16Z
- Files counted: **468** (all git-tracked `*.py` files)
- Total lines: **53,500**

Counts are raw `wc -l` (newline count). Files are grouped by top-level directory and sorted descending within each section. Regenerate with `python scripts/generate_loc_report.py`.

## Summary

| Section | Files | LOC |
|:--------|------:|----:|
| controllers | 13 | 1,412 |
| repositories | 51 | 4,057 |
| widgets | 176 | 20,672 |
| services | 72 | 7,525 |
| tests | 50 | 11,016 |
| automation | 19 | 3,223 |
| utils | 71 | 3,015 |
| other | 16 | 2,580 |

## controllers (13 files, 1,412 LOC)

| LOC | File |
|----:|:-----|
| 309 | `controllers/session_manager.py` |
| 173 | `controllers/app_controller/controller.py` |
| 135 | `controllers/app_controller/lifecycle.py` |
| 133 | `controllers/app_controller/bulk_data.py` |
| 121 | `controllers/app_controller/archetypes.py` |
| 121 | `controllers/app_controller/decks.py` |
| 98 | `controllers/app_controller/protocol.py` |
| 95 | `controllers/app_controller/settings.py` |
| 72 | `controllers/app_controller/ui_callbacks.py` |
| 50 | `controllers/app_controller/card_data.py` |
| 49 | `controllers/app_controller/collection.py` |
| 43 | `controllers/app_controller/__init__.py` |
| 13 | `controllers/__init__.py` |

## repositories (51 files, 4,057 LOC)

| LOC | File |
|----:|:-----|
| 383 | `repositories/deck_text_cache.py` |
| 334 | `repositories/scrapers/mtggoldfish.py` |
| 228 | `repositories/radar_repository/reads.py` |
| 156 | `repositories/card_repository/card_data_manager.py` |
| 148 | `repositories/card_repository/builder.py` |
| 141 | `repositories/deck_repository/database.py` |
| 141 | `repositories/metagame_repository/cache.py` |
| 137 | `repositories/format_card_pool_repository/reads.py` |
| 136 | `repositories/remote_snapshot_client/service.py` |
| 126 | `repositories/metagame_repository/deck_operations.py` |
| 125 | `repositories/radar_repository/writes.py` |
| 109 | `repositories/metagame_repository/archetype_resolution.py` |
| 108 | `repositories/card_repository/collection.py` |
| 93 | `repositories/deck_repository/ui_state.py` |
| 88 | `repositories/format_card_pool_repository/writes.py` |
| 76 | `repositories/deck_repository/filesystem.py` |
| 70 | `repositories/card_repository/storage.py` |
| 68 | `repositories/remote_snapshot_client/manifest.py` |
| 67 | `repositories/deck_repository/metadata_store.py` |
| 66 | `repositories/radar_repository/schema.py` |
| 63 | `repositories/scrapers/mtggoldfish_visual.py` |
| 62 | `repositories/card_repository/schemas.py` |
| 61 | `repositories/remote_snapshot_client/artifact.py` |
| 60 | `repositories/card_repository/protocol.py` |
| 59 | `repositories/card_repository/remote.py` |
| 57 | `repositories/remote_snapshot_client/http.py` |
| 54 | `repositories/metagame_repository/__init__.py` |
| 53 | `repositories/card_repository/__init__.py` |
| 51 | `repositories/card_repository/metadata.py` |
| 51 | `repositories/format_card_pool_repository/schema.py` |
| 51 | `repositories/metagame_repository/background.py` |
| 48 | `repositories/radar_repository/models.py` |
| 47 | `repositories/__init__.py` |
| 46 | `repositories/card_repository/state.py` |
| 45 | `repositories/metagame_repository/protocol.py` |
| 44 | `repositories/radar_repository/__init__.py` |
| 42 | `repositories/format_card_pool_repository/__init__.py` |
| 42 | `repositories/remote_snapshot_client/__init__.py` |
| 41 | `repositories/metagame_repository/repository.py` |
| 36 | `repositories/deck_repository/__init__.py` |
| 33 | `repositories/card_repository/repository.py` |
| 31 | `repositories/deck_repository/repository.py` |
| 25 | `repositories/format_card_pool_repository/models.py` |
| 24 | `repositories/deck_repository/protocol.py` |
| 23 | `repositories/format_card_pool_repository/repository.py` |
| 23 | `repositories/radar_repository/repository.py` |
| 21 | `repositories/remote_snapshot_client/protocol.py` |
| 20 | `repositories/metagame_repository/date_utils.py` |
| 15 | `repositories/format_card_pool_repository/protocol.py` |
| 15 | `repositories/radar_repository/protocol.py` |
| 14 | `repositories/scrapers/__init__.py` |

## widgets (176 files, 20,672 LOC)

| LOC | File |
|----:|:-----|
| 896 | `widgets/frames/app_frame/handlers/app_events.py` |
| 673 | `widgets/panels/deck_stats_panel/properties.py` |
| 657 | `widgets/panels/card_table_panel/table_view.py` |
| 651 | `widgets/frames/identify_opponent/handlers.py` |
| 620 | `widgets/panels/card_table_panel/pile_view.py` |
| 585 | `widgets/frames/app_frame/handlers/sideboard_guide.py` |
| 410 | `widgets/mana_icon_factory/svg_renderer.py` |
| 408 | `widgets/panels/card_inspector_panel/handlers.py` |
| 396 | `widgets/mana_icon_factory/bitmap_renderer.py` |
| 381 | `widgets/panels/card_table_panel/frame.py` |
| 367 | `widgets/frames/app_frame/handlers/app_frame.py` |
| 358 | `widgets/panels/card_panel/html_renderer.py` |
| 349 | `widgets/frames/metagame_analysis/handlers.py` |
| 343 | `widgets/panels/card_image_display/handlers.py` |
| 331 | `widgets/panels/mana_rich_text_ctrl/handlers.py` |
| 329 | `widgets/frames/match_history/handlers.py` |
| 313 | `widgets/frames/app_frame/handlers/card_tables.py` |
| 313 | `widgets/panels/card_box_panel/handlers.py` |
| 307 | `widgets/frames/radar/handlers.py` |
| 273 | `widgets/frames/timer_alert/handlers.py` |
| 269 | `widgets/panels/card_panel/handlers.py` |
| 245 | `widgets/lists/deck_results_list/handlers.py` |
| 239 | `widgets/mana_icon_factory/factory.py` |
| 232 | `widgets/frames/match_history/frame.py` |
| 231 | `widgets/panels/deck_builder_panel/handlers.py` |
| 227 | `widgets/panels/card_inspector_panel/frame.py` |
| 222 | `widgets/panels/card_table_panel/sorting.py` |
| 220 | `widgets/frames/metagame_analysis/frame.py` |
| 213 | `widgets/frames/identify_opponent/frame/calculator_panel.py` |
| 205 | `widgets/panels/deck_builder_panel/frame/advanced_filters.py` |
| 198 | `widgets/panels/card_table_panel/handlers.py` |
| 194 | `widgets/frames/radar/frame.py` |
| 193 | `widgets/frames/identify_opponent/frame/__init__.py` |
| 185 | `widgets/panels/mana_rich_text_ctrl/frame.py` |
| 175 | `widgets/frames/app_frame/frame/__init__.py` |
| 175 | `widgets/panels/sideboard_guide_panel/frame.py` |
| 172 | `widgets/frames/timer_alert/frame/sections.py` |
| 172 | `widgets/frames/top_cards/handlers.py` |
| 172 | `widgets/panels/deck_builder_panel/frame/search_results_view.py` |
| 169 | `widgets/panels/card_panel/frame.py` |
| 166 | `widgets/frames/app_frame/frame/center_panel.py` |
| 166 | `widgets/panels/deck_research_panel/frame/filters.py` |
| 163 | `widgets/dialogs/guide_entry_dialog/dialog.py` |
| 155 | `widgets/dialogs/image_download_dialog/handlers.py` |
| 152 | `widgets/frames/timer_alert/frame/__init__.py` |
| 147 | `widgets/panels/deck_research_panel/results_filter.py` |
| 142 | `widgets/panels/compact_radar_panel/handlers.py` |
| 137 | `widgets/dialogs/feedback_dialog/dialog.py` |
| 137 | `widgets/frames/rules_browser/frame.py` |
| 136 | `widgets/dialogs/image_download_dialog/dialog.py` |
| 135 | `widgets/panels/deck_notes_panel/frame/note_card_widget.py` |
| 131 | `widgets/frames/match_history/properties.py` |
| 130 | `widgets/dialogs/tutorial_dialog/dialog.py` |
| 129 | `widgets/panels/deck_builder_panel/frame/results_pane.py` |
| 129 | `widgets/panels/deck_notes_panel/handlers.py` |
| 124 | `widgets/panels/sideboard_card_selector/frame.py` |
| 122 | `widgets/frames/top_cards/frame.py` |
| 121 | `widgets/panels/deck_notes_panel/frame/__init__.py` |
| 120 | `widgets/frames/metagame_analysis/properties.py` |
| 116 | `widgets/frames/app_frame/frame/right_panel.py` |
| 115 | `widgets/panels/card_box_panel/frame.py` |
| 114 | `widgets/panels/deck_builder_panel/frame/__init__.py` |
| 113 | `widgets/panels/deck_builder_panel/frame/basic_filters.py` |
| 112 | `widgets/frames/identify_opponent/properties.py` |
| 110 | `widgets/frames/rules_browser/html_render.py` |
| 109 | `widgets/buttons/toolbar_buttons/panel.py` |
| 105 | `widgets/panels/sideboard_guide_panel/handlers.py` |
| 103 | `widgets/frames/app_frame/frame/left_panel.py` |
| 98 | `widgets/panels/compact_sideboard_panel/handlers.py` |
| 96 | `widgets/frames/app_frame/protocol.py` |
| 91 | `widgets/frames/identify_opponent/frame/load_archetype_dialog.py` |
| 89 | `widgets/panels/card_image_display/frame.py` |
| 85 | `widgets/frames/identify_opponent/frame/header.py` |
| 84 | `widgets/panels/deck_research_panel/frame/__init__.py` |
| 82 | `widgets/frames/timer_alert/properties.py` |
| 82 | `widgets/panels/deck_research_panel/frame/results_section.py` |
| 81 | `widgets/buttons/deck_action_buttons/panel.py` |
| 80 | `widgets/panels/deck_research_panel/handlers.py` |
| 78 | `widgets/frames/timer_alert/frame/threshold_panel.py` |
| 78 | `widgets/panels/deck_builder_panel/properties.py` |
| 77 | `widgets/dialogs/feedback_dialog/handlers.py` |
| 75 | `widgets/panels/card_box_panel/properties.py` |
| 73 | `widgets/buttons/mana_button/button.py` |
| 73 | `widgets/panels/card_image_display/properties.py` |
| 73 | `widgets/panels/deck_stats_panel/frame.py` |
| 72 | `widgets/panels/card_panel/properties.py` |
| 70 | `widgets/panels/card_panel/rule_popup.py` |
| 68 | `widgets/mana_icon_factory/resources.py` |
| 68 | `widgets/panels/compact_radar_panel/frame.py` |
| 65 | `widgets/panels/card_inspector_panel/protocol.py` |
| 64 | `widgets/frames/app_frame/properties.py` |
| 63 | `widgets/frames/mana_keyboard/frame.py` |
| 63 | `widgets/panels/deck_stats_panel/handlers.py` |
| 62 | `widgets/frames/splash_frame/frame.py` |
| 60 | `widgets/panels/deck_builder_panel/protocol.py` |
| 58 | `widgets/panels/sideboard_card_selector/handlers.py` |
| 56 | `widgets/panels/compact_sideboard_panel/frame.py` |
| 55 | `widgets/panels/card_panel/protocol.py` |
| 54 | `widgets/panels/deck_research_panel/protocol.py` |
| 52 | `widgets/panels/card_inspector_panel/properties.py` |
| 52 | `widgets/panels/sideboard_guide_panel/properties.py` |
| 48 | `widgets/frames/app_frame/handlers/ui_helpers.py` |
| 48 | `widgets/lists/deck_results_list/properties.py` |
| 48 | `widgets/panels/deck_research_panel/properties.py` |
| 47 | `widgets/frames/radar/properties.py` |
| 45 | `widgets/dialogs/guide_entry_dialog/properties.py` |
| 44 | `widgets/panels/mana_rich_text_ctrl/properties.py` |
| 43 | `widgets/frames/timer_alert/frame/styling.py` |
| 43 | `widgets/panels/card_box_panel/protocol.py` |
| 42 | `widgets/buttons/deck_action_buttons/properties.py` |
| 41 | `widgets/stylize.py` |
| 40 | `widgets/panels/card_table_panel/protocol.py` |
| 39 | `widgets/panels/card_table_panel/properties.py` |
| 37 | `widgets/dialogs/tutorial_dialog/handlers.py` |
| 37 | `widgets/frames/identify_opponent/__init__.py` |
| 36 | `widgets/panels/compact_radar_panel/properties.py` |
| 35 | `widgets/frames/splash_frame/handlers.py` |
| 35 | `widgets/mana_icon_factory/protocol.py` |
| 35 | `widgets/panels/deck_research_panel/frame/centered_choice.py` |
| 34 | `widgets/panels/sideboard_guide_panel/protocol.py` |
| 33 | `widgets/dialogs/help_dialog/dialog.py` |
| 33 | `widgets/panels/deck_notes_panel/protocol.py` |
| 33 | `widgets/panels/deck_stats_panel/protocol.py` |
| 32 | `widgets/buttons/deck_action_buttons/handlers.py` |
| 32 | `widgets/lists/deck_results_list/frame.py` |
| 31 | `widgets/frames/__init__.py` |
| 31 | `widgets/mana_icon_factory/__init__.py` |
| 30 | `widgets/panels/__init__.py` |
| 28 | `widgets/panels/deck_notes_panel/properties.py` |
| 27 | `widgets/panels/sideboard_card_selector/properties.py` |
| 26 | `widgets/frames/splash_frame/properties.py` |
| 26 | `widgets/frames/splash_frame/protocol.py` |
| 23 | `widgets/panels/compact_radar_panel/__init__.py` |
| 23 | `widgets/panels/compact_radar_panel/protocol.py` |
| 22 | `widgets/mana_icon_factory/cache.py` |
| 21 | `widgets/dialogs/image_download_dialog/properties.py` |
| 21 | `widgets/frames/app_frame/__init__.py` |
| 18 | `widgets/frames/top_cards/properties.py` |
| 18 | `widgets/panels/compact_sideboard_panel/protocol.py` |
| 16 | `widgets/frames/timer_alert/__init__.py` |
| 16 | `widgets/panels/deck_research_panel/__init__.py` |
| 15 | `widgets/dialogs/feedback_dialog/properties.py` |
| 15 | `widgets/panels/mana_rich_text_ctrl/keyboard_evts.py` |
| 13 | `widgets/dialogs/__init__.py` |
| 13 | `widgets/dialogs/guide_entry_dialog/handlers.py` |
| 13 | `widgets/frames/app_frame/handlers/__init__.py` |
| 11 | `widgets/frames/top_cards/__init__.py` |
| 10 | `widgets/buttons/__init__.py` |
| 8 | `widgets/dialogs/image_download_dialog/__init__.py` |
| 7 | `widgets/frames/mana_keyboard/__init__.py` |
| 7 | `widgets/frames/match_history/__init__.py` |
| 7 | `widgets/frames/metagame_analysis/__init__.py` |
| 7 | `widgets/frames/radar/__init__.py` |
| 7 | `widgets/frames/rules_browser/__init__.py` |
| 7 | `widgets/frames/splash_frame/__init__.py` |
| 7 | `widgets/lists/deck_results_list/__init__.py` |
| 7 | `widgets/panels/card_box_panel/__init__.py` |
| 7 | `widgets/panels/card_image_display/__init__.py` |
| 7 | `widgets/panels/card_inspector_panel/__init__.py` |
| 7 | `widgets/panels/card_panel/__init__.py` |
| 7 | `widgets/panels/card_table_panel/__init__.py` |
| 7 | `widgets/panels/compact_sideboard_panel/__init__.py` |
| 7 | `widgets/panels/deck_builder_panel/__init__.py` |
| 7 | `widgets/panels/deck_notes_panel/__init__.py` |
| 7 | `widgets/panels/deck_stats_panel/__init__.py` |
| 7 | `widgets/panels/mana_rich_text_ctrl/__init__.py` |
| 7 | `widgets/panels/sideboard_card_selector/__init__.py` |
| 7 | `widgets/panels/sideboard_guide_panel/__init__.py` |
| 5 | `widgets/buttons/deck_action_buttons/__init__.py` |
| 5 | `widgets/buttons/mana_button/__init__.py` |
| 5 | `widgets/buttons/toolbar_buttons/__init__.py` |
| 5 | `widgets/dialogs/feedback_dialog/__init__.py` |
| 5 | `widgets/dialogs/guide_entry_dialog/__init__.py` |
| 5 | `widgets/dialogs/help_dialog/__init__.py` |
| 5 | `widgets/dialogs/tutorial_dialog/__init__.py` |
| 5 | `widgets/lists/__init__.py` |

## services (72 files, 7,525 LOC)

| LOC | File |
|----:|:-----|
| 474 | `services/comp_rules_service.py` |
| 466 | `services/image_service/downloader.py` |
| 423 | `services/mtgo_bridge_service/client.py` |
| 345 | `services/image_service/disk_cache.py` |
| 282 | `services/image_service/download_queue.py` |
| 278 | `services/image_service/printing_index.py` |
| 235 | `services/gamelog_service/parser.py` |
| 183 | `services/bundle_snapshot_client/archetype_cache.py` |
| 175 | `services/image_service/schemas.py` |
| 171 | `services/collection_service/cache.py` |
| 170 | `services/deck_workflow_service.py` |
| 165 | `services/radar_service/analysis.py` |
| 164 | `services/gamelog_service/service.py` |
| 151 | `services/mtgo_bridge_service/__init__.py` |
| 139 | `services/gamelog_service/discovery.py` |
| 136 | `services/image_service/process_worker.py` |
| 130 | `services/deck_service/averager.py` |
| 126 | `services/image_service/path_resolver.py` |
| 124 | `services/gamelog_service/formats.py` |
| 119 | `services/bundle_snapshot_client/service.py` |
| 119 | `services/search_service/filtering.py` |
| 118 | `services/deck_service/parser.py` |
| 118 | `services/radar_service/card_stats.py` |
| 117 | `services/search_service/builder_search.py` |
| 97 | `services/deck_service/service.py` |
| 95 | `services/collection_service/bridge_refresh.py` |
| 93 | `services/bundle_snapshot_client/parser.py` |
| 88 | `services/image_service/__init__.py` |
| 79 | `services/collection_service/deck_analysis.py` |
| 77 | `services/__init__.py` |
| 77 | `services/image_service/metadata.py` |
| 73 | `services/gamelog_service/usernames.py` |
| 72 | `services/card_service.py` |
| 71 | `services/metagame_service.py` |
| 71 | `services/radar_service/precomputed.py` |
| 70 | `services/image_service/cache.py` |
| 69 | `services/search_service/deck_search.py` |
| 67 | `services/search_service/mana_query.py` |
| 65 | `services/gamelog_service/protocol.py` |
| 64 | `services/radar_service/export.py` |
| 63 | `services/image_service/bulk_data.py` |
| 63 | `services/image_service/workers.py` |
| 60 | `services/archetype_resolver.py` |
| 60 | `services/deck_service/text_builder.py` |
| 59 | `services/gamelog_service/__init__.py` |
| 57 | `services/bundle_snapshot_client/__init__.py` |
| 57 | `services/search_service/mana_filters.py` |
| 55 | `services/bundle_snapshot_client/http.py` |
| 54 | `services/image_service/service.py` |
| 51 | `services/search_service/basic_search.py` |
| 47 | `services/format_card_pool_service.py` |
| 46 | `services/collection_service/ownership.py` |
| 45 | `services/bundle_snapshot_client/snapshot_cache.py` |
| 45 | `services/collection_service/exporter.py` |
| 45 | `services/store_service.py` |
| 44 | `services/deck_service/__init__.py` |
| 43 | `services/bundle_snapshot_client/stamp.py` |
| 43 | `services/radar_service/__init__.py` |
| 42 | `services/collection_service/__init__.py` |
| 42 | `services/collection_service/stats.py` |
| 42 | `services/image_service/protocol.py` |
| 37 | `services/search_service/__init__.py` |
| 31 | `services/collection_service/protocol.py` |
| 31 | `services/radar_service/models.py` |
| 30 | `services/collection_service/service.py` |
| 30 | `services/radar_service/service.py` |
| 27 | `services/search_service/service.py` |
| 26 | `services/radar_service/protocol.py` |
| 25 | `services/collection_service/parsing.py` |
| 25 | `services/search_service/protocol.py` |
| 24 | `services/bundle_snapshot_client/protocol.py` |
| 20 | `services/deck_service/protocol.py` |

## tests (50 files, 11,016 LOC)

| LOC | File |
|----:|:-----|
| 980 | `tests/test_metagame_repository.py` |
| 678 | `tests/test_bundle_snapshot_client.py` |
| 671 | `tests/test_search_service.py` |
| 476 | `tests/test_results_filter.py` |
| 453 | `tests/test_card_images_cache.py` |
| 416 | `tests/test_radar_service.py` |
| 413 | `tests/test_comp_rules_service.py` |
| 405 | `tests/test_mtggoldfish.py` |
| 391 | `tests/test_gamelog_parser.py` |
| 385 | `tests/ui/conftest.py` |
| 364 | `tests/test_collection_service.py` |
| 270 | `tests/test_remote_snapshot_client.py` |
| 269 | `tests/test_card_repository.py` |
| 268 | `tests/test_card_panel_html_renderer.py` |
| 268 | `tests/test_identify_opponent_radar.py` |
| 263 | `tests/ui/test_deck_selector.py` |
| 242 | `tests/test_card_image_display_logic.py` |
| 233 | `tests/test_search_filters.py` |
| 221 | `tests/test_deck_workflow_service.py` |
| 214 | `tests/test_card_table_panel_sorting.py` |
| 212 | `tests/test_diagnostics.py` |
| 209 | `tests/test_math_utils.py` |
| 186 | `tests/test_card_data_refresh.py` |
| 183 | `tests/test_radar_card_stats.py` |
| 179 | `tests/test_deck_utils.py` |
| 173 | `tests/test_image_service.py` |
| 131 | `tests/test_paths.py` |
| 122 | `tests/test_session_manager.py` |
| 120 | `tests/test_deck_averager.py` |
| 119 | `tests/test_card_images_aliases.py` |
| 118 | `tests/test_background_worker.py` |
| 116 | `tests/test_deck_repository.py` |
| 114 | `tests/test_store_service.py` |
| 109 | `tests/test_timer_alert_async.py` |
| 101 | `tests/test_card_data_aliases.py` |
| 97 | `tests/test_rules_browser_html_render.py` |
| 91 | `tests/test_perf.py` |
| 89 | `tests/test_card_box_panel_logic.py` |
| 87 | `tests/test_i18n.py` |
| 83 | `tests/test_deck_service.py` |
| 83 | `tests/test_helpers.py` |
| 81 | `tests/test_runtime_flags.py` |
| 69 | `tests/test_archetype_resolver.py` |
| 60 | `tests/test_mana_icon_factory.py` |
| 53 | `tests/test_collection_loading.py` |
| 43 | `tests/test_opponent_detection.py` |
| 38 | `tests/test_card_panel_stats_lookup.py` |
| 33 | `tests/test_mtggoldfish_visual.py` |
| 19 | `tests/test_mtgo_bridge_client.py` |
| 18 | `tests/conftest.py` |

## automation (19 files, 3,223 LOC)

| LOC | File |
|----:|:-----|
| 1094 | `automation/server.py` |
| 606 | `automation/cli.py` |
| 370 | `automation/client.py` |
| 203 | `automation/e2e_tests/test_mana_input.py` |
| 183 | `automation/test_runner.py` |
| 135 | `automation/e2e_tests/test_builder.py` |
| 119 | `automation/e2e_tests/__init__.py` |
| 107 | `automation/e2e_tests/common.py` |
| 107 | `automation/e2e_tests/test_scrollbar.py` |
| 54 | `automation/e2e_tests/test_buttons.py` |
| 46 | `automation/e2e_tests/test_mana.py` |
| 43 | `automation/e2e_tests/test_images.py` |
| 42 | `automation/e2e_tests/test_widgets.py` |
| 33 | `automation/e2e_tests/test_golden.py` |
| 30 | `automation/e2e_tests/test_launch.py` |
| 25 | `automation/e2e_tests/test_notes.py` |
| 13 | `automation/__init__.py` |
| 8 | `automation/__main__.py` |
| 5 | `automation/e2e_tests/__main__.py` |

## utils (71 files, 3,015 LOC)

| LOC | File |
|----:|:-----|
| 472 | `utils/constants/__init__.py` |
| 180 | `utils/constants/paths.py` |
| 144 | `utils/diagnostics.py` |
| 132 | `utils/deck.py` |
| 120 | `utils/math_utils.py` |
| 114 | `utils/atomic_io.py` |
| 99 | `utils/constants/gameplay.py` |
| 85 | `utils/background_worker.py` |
| 85 | `utils/json_io.py` |
| 84 | `utils/constants/timing.py` |
| 75 | `utils/constants/ui_layout.py` |
| 57 | `utils/i18n/_en_us/app.py` |
| 57 | `utils/i18n/_pt_br/app.py` |
| 50 | `utils/constants/ui_images.py` |
| 45 | `utils/i18n/_en_us/__init__.py` |
| 45 | `utils/i18n/_pt_br/__init__.py` |
| 45 | `utils/logging_config.py` |
| 44 | `utils/i18n/_en_us/guide.py` |
| 44 | `utils/i18n/_pt_br/guide.py` |
| 41 | `utils/i18n/__init__.py` |
| 36 | `utils/constants/deck_rules.py` |
| 32 | `utils/i18n/_en_us/builder.py` |
| 32 | `utils/i18n/_pt_br/builder.py` |
| 30 | `utils/constants/formats.py` |
| 30 | `utils/i18n/_en_us/top_cards.py` |
| 30 | `utils/i18n/_pt_br/top_cards.py` |
| 30 | `utils/perf.py` |
| 29 | `utils/i18n/_en_us/match.py` |
| 29 | `utils/i18n/_pt_br/match.py` |
| 29 | `utils/image_effects.py` |
| 28 | `utils/i18n/_en_us/timer.py` |
| 28 | `utils/i18n/_pt_br/timer.py` |
| 27 | `utils/i18n/_en_us/tabs.py` |
| 27 | `utils/i18n/_pt_br/tabs.py` |
| 24 | `utils/i18n/_en_us/toolbar.py` |
| 24 | `utils/i18n/_pt_br/toolbar.py` |
| 23 | `utils/constants/keyboard.py` |
| 23 | `utils/i18n/_en_us/metagame.py` |
| 23 | `utils/i18n/_en_us/tutorial.py` |
| 23 | `utils/i18n/_pt_br/metagame.py` |
| 23 | `utils/i18n/_pt_br/tutorial.py` |
| 22 | `utils/constants/colors.py` |
| 22 | `utils/i18n/_en_us/research.py` |
| 22 | `utils/i18n/_pt_br/research.py` |
| 20 | `utils/constants/ui_timer.py` |
| 20 | `utils/i18n/_en_us/card_panel.py` |
| 20 | `utils/i18n/_pt_br/card_panel.py` |
| 18 | `utils/find_opponent_names.py` |
| 18 | `utils/i18n/_en_us/radar.py` |
| 18 | `utils/i18n/_pt_br/radar.py` |
| 17 | `utils/i18n/_en_us/tracker.py` |
| 17 | `utils/i18n/_pt_br/tracker.py` |
| 15 | `utils/constants/search.py` |
| 14 | `utils/runtime_flags.py` |
| 13 | `utils/constants/ui_windows.py` |
| 12 | `utils/i18n/_en_us/deck_actions.py` |
| 12 | `utils/i18n/_en_us/deck_results.py` |
| 12 | `utils/i18n/_en_us/notes.py` |
| 12 | `utils/i18n/_pt_br/deck_actions.py` |
| 12 | `utils/i18n/_pt_br/deck_results.py` |
| 12 | `utils/i18n/_pt_br/notes.py` |
| 11 | `utils/i18n/_en_us/window.py` |
| 11 | `utils/i18n/_pt_br/window.py` |
| 10 | `utils/constants/radar.py` |
| 10 | `utils/i18n/_en_us/rules_browser.py` |
| 10 | `utils/i18n/_pt_br/rules_browser.py` |
| 9 | `utils/constants/storage.py` |
| 9 | `utils/i18n/_en_us/bulk.py` |
| 9 | `utils/i18n/_pt_br/bulk.py` |
| 7 | `utils/constants/app.py` |
| 3 | `utils/constants/images.py` |

## other (16 files, 2,580 LOC)

| LOC | File |
|----:|:-----|
| 615 | `scripts/mtgosdk_repl.py` |
| 568 | `scripts/generate_dependency_diagrams.py` |
| 238 | `scripts/test_card_images.py` |
| 168 | `scripts/benchmark_json_caches.py` |
| 165 | `scripts/generate_loc_report.py` |
| 154 | `main.py` |
| 142 | `scripts/update_mtgosdk_vendor.py` |
| 141 | `scripts/monitor_currency.py` |
| 105 | `scripts/update_vendor_data.py` |
| 68 | `scripts/check_card_face_images.py` |
| 68 | `scripts/fetch_mana_assets.py` |
| 51 | `scripts/dump_collection.py` |
| 39 | `scripts/clear_caches.py` |
| 32 | `scripts/run_logged.py` |
| 26 | `setup.py` |
| 0 | `__init__.py` |

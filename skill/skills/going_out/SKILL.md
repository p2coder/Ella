---
name: going_out
description: Prepare a short reminder when the user is leaving, optionally using current visual context.
when_to_use: Use when the user is heading out; request camera_scene only when the task explicitly needs the current view.
allowed_roles: main_agent
required_tools: mock_weather, mock_checklist
optional_tools: camera_scene, mock_vision_summary
---

# going_out

This mock skill describes the capability needed for Ella Runtime MVP's MVP going-out reminder scenario.

It is intended for a SubAgent to load after strategy selection. The skill should help prepare a short, necessary reminder before the user leaves, using only provided task context such as the user's request, preference summary, and environment summary.

When the user explicitly asks Ella to inspect the current view, visible items, or camera scene, the SubAgent may choose one bounded `camera_scene` tool call. A normal going-out reminder does not require camera access.

This file is a skill definition only. It does not execute tools, inspect real camera input, call external APIs, write memory, or choose an execution strategy.

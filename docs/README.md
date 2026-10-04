# HW-PUPPET Documentation Index

This directory contains reference documentation and guides for HW-PUPPET firmware modules, hardware interfaces, and host utilities.

## Table of Contents

- [UART Bridge & Pattern Matcher API](uart_bridge_api.md)
  - C-level FreeRTOS streaming bridge (UART <-> TinyUSB CDC1)
  - Event-driven Multi-trigger Pattern Matcher (`uart_bridge.on_match`)
  - `Match` handle object lifecycle and context manager
  - Synchronous `wait_for` helper
  - Usage examples (Auto-reply, Boot Watcher, Debouncing)
- [Hardware Badge API](badge_api.md)
  - Persistent hardware identifier stored in ESP32-S3 NVS
  - MicroPython C module API (`get_badge`, `set_badge`, `info`)
  - Host CLI utility (`tools/badge.py`)
  - Multi-puppet orchestration with `ae-hw-bridge`

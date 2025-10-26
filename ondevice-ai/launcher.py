#!/usr/bin/env python
"""Graphical launcher that embeds the automation daemon inside a WebKit window."""
from __future__ import annotations

import atexit
import json
import platform
import sys
import textwrap
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

import webview

import grpc

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc
from core.config import (
    apply_model_profile,
    delete_quick_goal,
    get_config,
    list_model_modes,
    list_model_profiles,
    list_quick_goals,
    save_config,
    save_quick_goal,
    set_model_mode,
)
from core.audit import read_events
from core.vector_store import VectorStore
from core.sandbox import SandboxPermissions

from automation_daemon import DaemonHandle, start_daemon


PB = cast(Any, pb_module)


HTML_TEMPLATE = textwrap.dedent(
    """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>OnDeviceAI</title>
        <style>
            :root {
                color-scheme: light dark;
                font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, sans-serif;
                background: radial-gradient(circle at top left, #1e3a8a 0%, #0f172a 45%, #020617 100%);
                height: 100%;
                margin: 0;
            }
            body {
                background: transparent;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 26px;
                box-sizing: border-box;
            }
            .app {
                display: grid;
                grid-template-columns: 320px minmax(520px, 1fr);
                gap: 26px;
                max-width: 1180px;
                width: 100%;
                margin: 0 auto;
            }
            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 22px;
            }
            .main {
                display: flex;
                flex-direction: column;
                gap: 22px;
            }
            .shell {
                display: flex;
                flex-direction: column;
                gap: 22px;
                max-width: 1260px;
                width: 100%;
                margin: 0 auto;
            }
            .topbar {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-end;
                gap: 18px;
            }
            .brand {
                flex: 1 1 260px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .brand h1 {
                margin: 0;
                font-size: 28px;
                letter-spacing: -0.01em;
            }
            .brand-subtitle {
                font-size: 14px;
                opacity: 0.7;
            }
            .topbar-metrics {
                display: flex;
                gap: 12px;
            }
            .tab-bar {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 8px;
                border-radius: 999px;
                background: rgba(15, 23, 42, 0.55);
                box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
            }
            .tab-button {
                appearance: none;
                border: none;
                border-radius: 999px;
                background: transparent;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                color: #94a3b8;
                cursor: pointer;
                transition: all 140ms ease;
            }
            .tab-button:hover {
                color: #f8fafc;
            }
            .tab-button.active {
                background: linear-gradient(135deg, #2563eb, #38bdf8);
                color: #fff;
                box-shadow: 0 14px 32px rgba(37, 99, 235, 0.35);
            }
            .content {
                display: flex;
                flex-direction: column;
                gap: 22px;
            }
            .tab-panel {
                display: none;
                flex-direction: column;
                gap: 22px;
            }
            .tab-panel.active {
                display: flex;
            }
            .grid {
                display: grid;
                gap: 22px;
            }
            .grid-two {
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            }
            .grid-balanced {
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            }
            .hero-grid {
                margin-top: 18px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 18px;
            }
            .section-subtitle {
                text-transform: uppercase;
                letter-spacing: 0.1em;
                font-size: 11px;
                opacity: 0.6;
                margin-bottom: 6px;
            }
            .compact-card {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            .compact-card .stack {
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            .compact-card .divider {
                height: 1px;
                background: rgba(148, 163, 184, 0.16);
                margin: 4px 0;
            }
            .inline-actions {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }
            .knowledge-layout {
                display: grid;
                grid-template-columns: minmax(260px, 1fr) minmax(320px, 1.1fr);
                gap: 18px;
                align-items: start;
            }
            .knowledge-table-wrapper {
                position: relative;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .knowledge-table {
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-height: 360px;
                overflow-y: auto;
            }
            .knowledge-row {
                border-radius: 14px;
                padding: 12px 14px;
                background: rgba(15, 23, 42, 0.45);
                cursor: pointer;
                transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
            }
            .knowledge-row:hover {
                transform: translateY(-1px);
                background: rgba(37, 99, 235, 0.18);
            }
            .knowledge-row.active {
                background: rgba(37, 99, 235, 0.26);
                box-shadow: 0 14px 30px rgba(37, 99, 235, 0.28);
            }
            .knowledge-row h4 {
                margin: 0;
                font-size: 14px;
                font-weight: 600;
            }
            .knowledge-row .meta {
                font-size: 12px;
                opacity: 0.65;
                margin: 4px 0 8px;
            }
            .knowledge-row .preview {
                font-size: 13px;
                opacity: 0.8;
                line-height: 1.5;
            }
            .knowledge-detail {
                background: rgba(15, 23, 42, 0.45);
                border-radius: 16px;
                padding: 16px;
                min-height: 260px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .knowledge-detail pre {
                max-height: 240px;
                overflow-y: auto;
            }
            .knowledge-toolbar {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            .knowledge-summary {
                font-size: 12px;
                opacity: 0.7;
            }
            .detail-footer {
                margin-top: 12px;
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 12px;
                font-size: 12px;
                opacity: 0.7;
            }
            .detail-footer button {
                padding: 8px 14px;
                font-size: 13px;
            }
            .status-line {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                font-size: 13px;
            }
            .status-line.success {
                color: #bbf7d0;
            }
            .status-line.error {
                color: #fecaca;
            }
            .spinner {
                width: 16px;
                height: 16px;
                border-radius: 50%;
                border: 2px solid rgba(59, 130, 246, 0.25);
                border-top-color: #38bdf8;
                animation: spin 0.75s linear infinite;
            }
            @keyframes spin {
                to {
                    transform: rotate(360deg);
                }
            }
            .card {
                background: rgba(15, 23, 42, 0.88);
                border-radius: 20px;
                padding: 24px;
                box-shadow: 0 20px 48px rgba(15, 23, 42, 0.55);
                color: #f8fafc;
                backdrop-filter: blur(24px);
            }
            .hero-card h1 {
                margin: 0;
                font-size: 26px;
                letter-spacing: -0.01em;
            }
            .hero-card p {
                margin: 6px 0 18px;
                opacity: 0.72;
                font-size: 15px;
                line-height: 1.4;
            }
            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 10px 14px;
                border-radius: 999px;
                background: linear-gradient(135deg, rgba(37, 99, 235, 0.32), rgba(14, 165, 233, 0.28));
                font-size: 14px;
                font-weight: 600;
            }
            .metrics {
                margin-top: 20px;
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
            }
            .metric {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 14px;
            }
            .metric-label {
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                opacity: 0.6;
                display: block;
            }
            .metric-value {
                font-size: 22px;
                font-weight: 700;
                margin-top: 4px;
            }
            .endpoints {
                margin-top: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                font-size: 13px;
            }
            .endpoint-label {
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 11px;
                opacity: 0.6;
            }
            .endpoint-value {
                margin-top: 6px;
                padding: 8px 10px;
                border-radius: 10px;
                background: rgba(15, 23, 42, 0.6);
                font-family: "SFMono-Regular", ui-monospace, Menlo, monospace;
                word-break: break-all;
                color: #cbd5f5;
            }
            .last-event {
                margin-top: 18px;
                font-size: 13px;
                line-height: 1.5;
                background: rgba(37, 99, 235, 0.18);
                border-radius: 14px;
                padding: 14px;
            }
            .section-title {
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                opacity: 0.6;
                margin-bottom: 12px;
            }
            select,
            textarea,
            input[type="text"],
            input[type="search"] {
                appearance: none;
                width: 100%;
                border: none;
                border-radius: 14px;
                padding: 12px 14px;
                font-size: 14px;
                background: rgba(15, 23, 42, 0.65);
                color: #e2e8f0;
                font-family: "SFMono-Regular", ui-monospace, Menlo, monospace;
                box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.16);
                box-sizing: border-box;
            }
            select:focus,
            textarea:focus,
            input:focus {
                outline: none;
                box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.45);
            }
            textarea {
                resize: vertical;
                min-height: 120px;
            }
            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .chip {
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                padding: 5px 10px;
                border-radius: 999px;
                background: rgba(37, 99, 235, 0.28);
                color: #bfdbfe;
            }
            .chip.error {
                background: rgba(239, 68, 68, 0.28);
                color: #fecaca;
            }
            .toggle {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .switch {
                position: relative;
                display: inline-block;
                width: 48px;
                height: 26px;
            }
            .switch input {
                opacity: 0;
                width: 0;
                height: 0;
            }
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: rgba(100, 116, 139, 0.55);
                transition: 0.2s;
                border-radius: 34px;
            }
            .slider:before {
                position: absolute;
                content: "";
                height: 20px;
                width: 20px;
                left: 3px;
                bottom: 3px;
                background-color: #0f172a;
                transition: 0.2s;
                border-radius: 50%;
                box-shadow: 0 4px 8px rgba(15, 23, 42, 0.4);
            }
            input:checked + .slider {
                background: linear-gradient(135deg, #22d3ee, #2563eb);
            }
            input:checked + .slider:before {
                transform: translateX(22px);
                background: white;
            }
            .card-actions {
                display: flex;
                justify-content: flex-end;
                gap: 12px;
                flex-wrap: wrap;
                margin-top: 18px;
            }
            button {
                appearance: none;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 120ms ease, box-shadow 120ms ease;
            }
            button.primary {
                background: linear-gradient(135deg, #2563eb, #3b82f6);
                color: white;
                box-shadow: 0 12px 24px rgba(37, 99, 235, 0.35);
            }
            button.secondary {
                background: rgba(15, 23, 42, 0.7);
                color: #cbd5f5;
            }
            button.ghost {
                background: rgba(148, 163, 184, 0.18);
                color: #e2e8f0;
            }
            button:hover {
                transform: translateY(-1px);
            }
            button:disabled {
                opacity: 0.55;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            .split {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
            }
            .doc-item,
            .activity-item {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 14px;
                font-size: 13px;
                line-height: 1.5;
            }
            .doc-title,
            .activity-type {
                font-weight: 600;
                margin-bottom: 6px;
                font-size: 13px;
            }
            .doc-meta,
            .activity-meta {
                opacity: 0.65;
                font-size: 12px;
                margin-bottom: 6px;
            }
            pre {
                background: rgba(15, 23, 42, 0.45);
                border-radius: 12px;
                padding: 12px;
                font-size: 12px;
                overflow-x: auto;
                color: #e2e8f0;
                box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
            }
            .plan-steps {
                margin-top: 16px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .plan-step {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 14px;
                font-size: 13px;
                line-height: 1.5;
            }
            .plan-step-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 14px;
                margin-bottom: 8px;
            }
            .plan-step-meta {
                font-size: 12px;
                opacity: 0.65;
                display: flex;
                gap: 10px;
            }
            .empty-state {
                padding: 18px;
                border-radius: 14px;
                background: rgba(15, 23, 42, 0.45);
                font-size: 13px;
                opacity: 0.75;
            }
            .log-stream {
                max-height: 260px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .log-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 12px;
                font-size: 12px;
                opacity: 0.8;
            }
            .log-scroll {
                max-height: 260px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .log-entry {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 12px;
                padding: 12px;
                font-size: 12px;
                line-height: 1.5;
                border-left: 3px solid rgba(148, 163, 184, 0.4);
            }
            .log-entry.error {
                border-left-color: rgba(248, 113, 113, 0.8);
                background: rgba(153, 27, 27, 0.28);
            }
            .log-entry.success {
                border-left-color: rgba(34, 197, 94, 0.75);
                background: rgba(22, 101, 52, 0.25);
            }
            .log-entry .log-header {
                display: flex;
                justify-content: space-between;
                gap: 10px;
                font-weight: 600;
            }
            .log-entry time {
                font-size: 11px;
                opacity: 0.65;
            }
            .metrics-grid {
                margin-top: 12px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 12px;
            }
            .metric-card {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 14px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            .metric-card h3 {
                margin: 0;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                opacity: 0.65;
            }
            .metric-value-large {
                font-size: 26px;
                font-weight: 600;
            }
            .progress {
                position: relative;
                height: 8px;
                border-radius: 999px;
                background: rgba(148, 163, 184, 0.25);
                overflow: hidden;
            }
            .progress-bar {
                position: absolute;
                top: 0;
                left: 0;
                bottom: 0;
                background: linear-gradient(135deg, #2563eb, #38bdf8);
            }
            .dashboard-meta {
                margin-top: 12px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 12px;
                font-size: 13px;
            }
            .dashboard-meta div {
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 12px 14px;
                line-height: 1.5;
            }
            .dashboard-events {
                margin-top: 14px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .dashboard-event {
                background: rgba(15, 23, 42, 0.45);
                border-radius: 12px;
                padding: 12px;
                font-size: 12px;
                line-height: 1.5;
            }
            .quick-layout {
                display: grid;
                grid-template-columns: minmax(200px, 260px) minmax(0, 1fr);
                gap: 16px;
            }
            .quick-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-height: 320px;
                overflow-y: auto;
            }
            .quick-item {
                border-radius: 12px;
                padding: 12px;
                background: rgba(15, 23, 42, 0.45);
                cursor: pointer;
                transition: transform 120ms ease, background 120ms ease;
            }
            .quick-item:hover {
                transform: translateY(-1px);
                background: rgba(37, 99, 235, 0.25);
            }
            .quick-item.active {
                background: rgba(37, 99, 235, 0.35);
                box-shadow: 0 10px 24px rgba(37, 99, 235, 0.25);
            }
            .quick-item h4 {
                margin: 0;
                font-size: 14px;
                font-weight: 600;
            }
            .quick-item p {
                margin: 4px 0 0;
                opacity: 0.65;
                font-size: 12px;
            }
            .quick-detail {
                background: rgba(15, 23, 42, 0.45);
                border-radius: 14px;
                padding: 16px;
                min-height: 240px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .quick-detail h3 {
                margin: 0;
                font-size: 16px;
            }
            .quick-fields {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .quick-actions {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            .permissions-list {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .permissions-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                background: rgba(15, 23, 42, 0.45);
                border-radius: 12px;
                padding: 12px 14px;
            }
            .quick-form {
                margin-top: 18px;
                padding: 16px;
                border-radius: 14px;
                background: rgba(15, 23, 42, 0.45);
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .quick-form h4 {
                margin: 0;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                opacity: 0.6;
            }
            .quick-form-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 12px;
            }
            .quick-form textarea {
                min-height: 120px;
            }
            @media (max-width: 1080px) {
                body {
                    padding: 18px;
                }
                .topbar {
                    flex-direction: column;
                    align-items: stretch;
                }
                .topbar-metrics {
                    width: 100%;
                    justify-content: space-between;
                }
                .knowledge-layout {
                    grid-template-columns: 1fr;
                }
                .knowledge-table {
                    max-height: none;
                }
            }
        </style>
    </head>
    <body>
        <div class="shell">
            <header class="topbar">
                <div class="brand">
                    <h1>OnDeviceAI Control Center</h1>
                    <div class="brand-subtitle">Local-first automation cockpit with observability and knowledge tools.</div>
                    <div class="status-pill" id="status-label">Preparing backend…</div>
                </div>
                <div class="topbar-metrics">
                    <div class="metric">
                        <span class="metric-label">Documents</span>
                        <span class="metric-value" id="metric-docs">0</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Recent Events</span>
                        <span class="metric-value" id="metric-events">0</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">CPU Usage</span>
                        <span class="metric-value" id="metric-cpu">—</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Memory Usage</span>
                        <span class="metric-value" id="metric-memory">—</span>
                    </div>
                </div>
                <nav class="tab-bar">
                    <button class="tab-button active" data-tab="overview">Overview</button>
                    <button class="tab-button" data-tab="automations">Automations</button>
                    <button class="tab-button" data-tab="knowledge">Knowledge</button>
                </nav>
            </header>

            <main class="content">
                <section class="tab-panel active" data-tab="overview">
                    <div class="grid grid-two">
                        <div class="card hero-card">
                            <h1>System Status</h1>
                            <p>Track runtime health, connection points, and the latest activity at a glance.</p>
                            <div class="hero-grid">
                                <div>
                                    <div class="section-subtitle">Runtime URL</div>
                                    <div class="endpoint-value" id="status-runtime">—</div>
                                </div>
                                <div>
                                    <div class="section-subtitle">gRPC Endpoint</div>
                                    <div class="endpoint-value" id="status-grpc">—</div>
                                </div>
                            </div>
                            <div class="last-event" id="last-event">Waiting for activity…</div>
                        </div>
                        <div class="card compact-card">
                            <div class="section-title">Model & Intelligence Mode</div>
                            <div class="stack">
                                <div>
                                    <div class="section-subtitle">Model Profile</div>
                                    <select id="profile-select" onchange="changeProfile(event)"></select>
                                    <div style="margin-top: 12px; font-size: 13px;" id="profile-details">Loading model profiles…</div>
                                </div>
                                <div class="divider"></div>
                                <div>
                                    <div class="section-subtitle">Intelligence Mode</div>
                                    <div class="toggle" style="margin-bottom: 10px;">
                                        <label class="switch">
                                            <input type="checkbox" id="mode-toggle" onchange="toggleMode(event)" />
                                            <span class="slider"></span>
                                        </label>
                                        <span id="mode-label" style="font-size: 13px; opacity: 0.75;">Checking…</span>
                                    </div>
                                    <div style="font-size: 13px; line-height: 1.5;" id="mode-details">Determining available modes…</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card" id="operations-card">
                        <div class="section-title">Operations Dashboard</div>
                        <div class="metrics-grid" id="metrics-grid">
                            <div class="empty-state">Gathering system metrics…</div>
                        </div>
                        <div class="dashboard-meta" id="metrics-meta"></div>
                        <div class="section-title" style="margin-top:18px;">Latest Activity</div>
                        <div class="dashboard-events" id="dashboard-events"></div>
                    </div>

                    <div class="grid grid-two">
                        <div class="card">
                            <div class="section-title">Quick Index</div>
                            <textarea id="quick-index-text" placeholder="Drop notes, transcripts, or raw text to index instantly"></textarea>
                            <div class="card-actions">
                                <button class="ghost" onclick="document.getElementById('quick-index-text').value='';">Clear</button>
                                <button class="primary" onclick="indexSnippet()">Add to Knowledge</button>
                            </div>
                            <div class="empty-state" id="knowledge-status">Idle.</div>
                        </div>
                        <div class="card">
                            <div class="section-title">System Permissions</div>
                            <div class="permissions-list" id="permissions-list">
                                <div class="empty-state">Loading permissions…</div>
                            </div>
                            <div id="permissions-status" style="margin-top:12px; font-size:12px; opacity:0.7;"></div>
                        </div>
                        <div class="card" id="runtime-pool-card">
                            <div class="section-title">Runtime Pool</div>
                            <div class="runtime-pool-grid" id="runtime-pool-grid">
                                <div class="empty-state">Pool not enabled.</div>
                            </div>
                        </div>
                        <div class="card" id="sandbox-card">
                            <div class="section-title">Sandbox</div>
                            <div class="sandbox-grid" id="sandbox-grid">
                                <div class="empty-state">Collecting sandbox telemetry…</div>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="section-title">Activity Stream</div>
                        <div class="empty-state" id="activity-status">Listening for new events…</div>
                        <div class="log-stream" id="activity-feed"></div>
                    </div>

                    <div class="card">
                        <div class="section-title">Execution Logs</div>
                        <div class="log-toolbar">
                            <span id="logs-count">No entries</span>
                            <button class="ghost" onclick="loadLogs()">Refresh</button>
                        </div>
                        <div class="log-scroll" id="logs-feed">
                            <div class="empty-state">Fetching logs…</div>
                        </div>
                    </div>
                </section>

                <section class="tab-panel" data-tab="automations">
                    <div class="card">
                        <div class="section-title">Automation Planner</div>
                        <textarea id="goal" placeholder="Describe a rich automation objective. The assistant will propose sequenced actions."></textarea>
                        <div class="card-actions">
                            <button class="secondary" onclick="quitApp()">Quit</button>
                            <button class="ghost" onclick="runPlan()">Preview Plan</button>
                            <button class="primary" onclick="runAgent()">Run Autonomously</button>
                        </div>
                        <div class="empty-state" id="plan-status">No plan generated yet.</div>
                        <div class="plan-steps" id="plan-results"></div>
                    </div>

                    <div class="card">
                        <div class="section-title">Quick Automations</div>
                        <div class="quick-layout">
                            <div class="quick-list" id="quick-goal-list"></div>
                            <div class="quick-detail" id="quick-goal-detail">
                                <div class="empty-state">Select an automation to view details.</div>
                            </div>
                        </div>
                        <div class="quick-form">
                            <h4>Create Custom Automation</h4>
                            <div class="quick-form-grid">
                                <input type="text" id="new-quick-label" placeholder="Label" />
                                <input type="text" id="new-quick-category" placeholder="Category" />
                                <select id="new-quick-mode">
                                    <option value="plan" selected>Plan only</option>
                                    <option value="auto">Autonomous run</option>
                                </select>
                            </div>
                            <input type="text" id="new-quick-fields" placeholder="Fields (comma separated, e.g. topic,deadline)" />
                            <textarea id="new-quick-description" placeholder="Short description"></textarea>
                            <textarea id="new-quick-goal" placeholder="Describe the automation goal. Use {{field}} to reference user inputs."></textarea>
                            <div class="quick-actions">
                                <button class="primary" onclick="createQuickGoal()">Save Automation</button>
                                <div id="quick-form-status" style="font-size:12px; opacity:0.7;"></div>
                            </div>
                        </div>
                    </div>
                </section>

                <section class="tab-panel" data-tab="knowledge">
                    <div class="card">
                        <div class="inline-actions">
                            <div>
                                <div class="section-title" style="margin-bottom:6px;">Knowledge Workspace</div>
                                <div class="knowledge-summary" id="knowledge-count">0 documents indexed</div>
                            </div>
                            <div class="knowledge-toolbar">
                                <button class="ghost" onclick="loadDocuments()">Refresh</button>
                                <button class="ghost" onclick="deleteSelectedDocument()">Delete Selected</button>
                                <button class="ghost" onclick="clearKnowledge()">Clear All</button>
                            </div>
                        </div>
                        <div class="knowledge-layout">
                            <div class="knowledge-table-wrapper">
                                <div class="knowledge-table" id="knowledge-table"></div>
                                <div class="empty-state" id="knowledge-empty" style="display:none;">No indexed documents stored yet.</div>
                            </div>
                            <div class="knowledge-detail" id="knowledge-detail">
                                <div class="empty-state">Select a document to inspect its full content.</div>
                            </div>
                        </div>
                        <div class="detail-footer">
                            <button class="ghost" onclick="copyDocumentContent()">Copy content</button>
                            <div id="knowledge-detail-status"></div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="section-title">Semantic Query</div>
                        <input type="search" id="query-input" placeholder="Ask the vector store…" />
                        <div class="card-actions">
                            <button class="primary" onclick="runQuery()">Search</button>
                        </div>
                        <div class="empty-state" id="query-status">No query executed.</div>
                        <div class="plan-steps" id="query-results"></div>
                    </div>
                </section>
            </main>
        </div>

        <script>
            let profiles = [];
            let activeProfile = null;
            let modes = [];
            let activeMode = null;
            let currentPlan = [];
            let planExecution = {};
            let dashboardState = {};
            let quickGoals = [];
            let activeQuickGoal = null;
            let permissionsState = {};
            let activeDocumentId = null;
            let currentDocumentDetail = null;
            let runtimePoolState = null;
            let sandboxState = null;

            function formatIso(ts) {
                if (!ts) {
                    return '—';
                }
                try {
                    const date = new Date(ts);
                    if (!isNaN(date.getTime())) {
                        return date.toLocaleString();
                    }
                } catch (err) {
                    return ts;
                }
                return ts;
            }

            function setPlanStatus(message, options = {}) {
                const statusEl = document.getElementById('plan-status');
                if (!statusEl) {
                    return;
                }
                const tone = options.tone || 'default';
                const loading = Boolean(options.loading);
                const classes = ['status-line'];
                if (tone === 'success') {
                    classes.push('success');
                } else if (tone === 'error') {
                    classes.push('error');
                }
                const spinnerMarkup = loading ? '<span class="spinner"></span>' : '';
                statusEl.innerHTML = `<div class="${classes.join(' ')}">${spinnerMarkup}<span>${message}</span></div>`;
            }

            function initTabs() {
                const buttons = document.querySelectorAll('.tab-button');
                buttons.forEach((button) => {
                    button.addEventListener('click', () => {
                        const tab = button.dataset.tab;
                        activateTab(tab);
                    });
                });
                const stored = window.localStorage ? window.localStorage.getItem('mahi.activeTab') : null;
                activateTab(stored || 'overview');
            }

            function activateTab(tabName) {
                if (!tabName) {
                    return;
                }
                document.querySelectorAll('.tab-button').forEach((button) => {
                    button.classList.toggle('active', button.dataset.tab === tabName);
                });
                document.querySelectorAll('.tab-panel').forEach((panel) => {
                    panel.classList.toggle('active', panel.dataset.tab === tabName);
                });
                try {
                    if (window.localStorage) {
                        window.localStorage.setItem('mahi.activeTab', tabName);
                    }
                } catch (err) {
                    // storage may be unavailable; ignore
                }
            }

            function renderStatus(payload) {
                const label = payload.profile_label ? `${payload.status} • ${payload.profile_label}` : payload.status;
                document.getElementById('status-label').innerText = label;
                document.getElementById('status-runtime').innerText = payload.runtime || '—';
                document.getElementById('status-grpc').innerText = payload.grpc || '—';
                document.getElementById('metric-docs').innerText = payload.documents ?? 0;
                document.getElementById('metric-events').innerText = payload.event_count ?? 0;
                const cpuMetric = document.getElementById('metric-cpu');
                const memoryMetric = document.getElementById('metric-memory');
                const fallbackMetrics = dashboardState && dashboardState.metrics ? dashboardState.metrics : {};
                const cpuValue = typeof payload.cpu_percent === 'number'
                    ? payload.cpu_percent
                    : (typeof fallbackMetrics.cpu_percent === 'number' ? fallbackMetrics.cpu_percent : null);
                const memoryValue = typeof payload.memory_percent === 'number'
                    ? payload.memory_percent
                    : (typeof fallbackMetrics.memory_percent === 'number' ? fallbackMetrics.memory_percent : null);
                if (cpuMetric) {
                    cpuMetric.innerText = typeof cpuValue === 'number'
                        ? `${Math.round(Math.max(0, Math.min(100, cpuValue)))}%`
                        : '—';
                }
                if (memoryMetric) {
                    memoryMetric.innerText = typeof memoryValue === 'number'
                        ? `${Math.round(Math.max(0, Math.min(100, memoryValue)))}%`
                        : '—';
                }
                if (payload.last_event && payload.last_event.payload) {
                    const evt = payload.last_event;
                    document.getElementById('last-event').innerHTML = `
                        <div style="font-weight:600; margin-bottom:6px;">${evt.type}</div>
                        <div style="opacity:0.75;">${formatIso(evt.ts)}</div>
                        <pre style="margin-top:8px; white-space: pre-wrap;">${JSON.stringify(evt.payload, null, 2)}</pre>
                    `;
                } else {
                    document.getElementById('last-event').innerText = 'Waiting for activity…';
                }
                if (payload.runtime_pool) {
                    runtimePoolState = payload.runtime_pool;
                    renderRuntimePool(runtimePoolState);
                }
                if (payload.sandbox) {
                    sandboxState = payload.sandbox;
                    renderSandbox(sandboxState);
                }
            }

            async function refresh() {
                try {
                    const payload = await window.pywebview.api.status();
                    renderStatus(payload);
                    if (payload.profile && payload.profile !== activeProfile) {
                        activeProfile = payload.profile;
                        const select = document.getElementById('profile-select');
                        if (!select.disabled && select.value !== activeProfile) {
                            select.value = activeProfile;
                            renderProfileDetails(activeProfile);
                        }
                    }
                    if (payload.mode && payload.mode !== activeMode) {
                        activeMode = payload.mode;
                        syncModeToggle();
                    }
                } catch (err) {
                    document.getElementById('status-label').innerText = `Status unavailable: ${err}`;
                }
            }

            function renderProfileDetails(profileId) {
                const details = document.getElementById('profile-details');
                if (!profiles.length) {
                    details.innerText = 'No models available. Check configuration.';
                    return;
                }
                const next = profiles.find((profile) => profile.id === profileId);
                if (!next) {
                    details.innerText = 'Select a model profile to view details.';
                    return;
                }
                const capabilities = (next.capabilities || []).map((cap) => `<span class="chip">${cap}</span>`).join('');
                details.innerHTML = `
                    <div style="font-weight:600; font-size:15px; margin-bottom:6px;">${next.label}</div>
                    <div style="opacity:0.75; margin-bottom:10px; line-height:1.5;">${next.description || 'No description provided.'}</div>
                    <div class="chips">${capabilities || '<span class="chip">custom</span>'}</div>
                `;
            }

            async function loadProfiles() {
                const select = document.getElementById('profile-select');
                select.disabled = true;
                document.getElementById('profile-details').innerText = 'Loading model profiles…';
                try {
                    const payload = await window.pywebview.api.model_profiles();
                    const receivedProfiles = payload && Array.isArray(payload.profiles) ? payload.profiles : [];
                    profiles = receivedProfiles;
                    activeProfile = payload && typeof payload.active === 'string' ? payload.active : (profiles[0] ? profiles[0].id : null);
                    select.innerHTML = '';
                    for (const profile of profiles) {
                        if (!profile || !profile.id) {
                            continue;
                        }
                        const option = document.createElement('option');
                        option.value = profile.id;
                        option.textContent = profile.label || profile.id;
                        select.appendChild(option);
                    }
                    if (activeProfile && profiles.some((profile) => profile && profile.id === activeProfile)) {
                        select.value = activeProfile;
                    } else if (profiles.length) {
                        select.value = profiles[0].id;
                        activeProfile = profiles[0].id;
                    }
                    renderProfileDetails(select.value);
                } catch (err) {
                    select.innerHTML = '';
                    document.getElementById('profile-details').innerText = `Failed to load model profiles: ${err}`;
                    profiles = [];
                    activeProfile = null;
                } finally {
                    select.disabled = !profiles.length;
                }
            }

            function renderModeDetails(modeId) {
                const details = document.getElementById('mode-details');
                const label = document.getElementById('mode-label');
                if (!modes.length) {
                    details.innerText = 'No modes available.';
                    label.innerText = 'Unavailable';
                    return;
                }
                const current = modes.find((mode) => mode.id === modeId);
                if (!current) {
                    details.innerText = 'Select a mode to view details.';
                    label.innerText = 'Unknown';
                    return;
                }
                label.innerText = current.label || current.id;
                const caps = (current.capabilities || []).map((cap) => `<span class="chip">${cap}</span>`).join('');
                details.innerHTML = `
                    <div style="font-weight:600; font-size:15px; margin-bottom:6px;">${current.label}</div>
                    <div style="opacity:0.75; margin-bottom:10px; line-height:1.5;">${current.description || 'No description provided.'}</div>
                    <div class="chips">${caps || '<span class="chip">standard</span>'}</div>
                `;
            }

            function syncModeToggle() {
                const toggle = document.getElementById('mode-toggle');
                if (!toggle) {
                    return;
                }
                toggle.checked = activeMode !== 'rules';
                renderModeDetails(activeMode);
            }

            async function loadModes() {
                const details = document.getElementById('mode-details');
                const label = document.getElementById('mode-label');
                const toggle = document.getElementById('mode-toggle');
                toggle.disabled = true;
                details.innerText = 'Loading modes…';
                label.innerText = 'Checking…';
                try {
                    const payload = await window.pywebview.api.model_modes();
                    modes = payload.modes || [];
                    activeMode = payload.active || 'ml';
                    syncModeToggle();
                } catch (err) {
                    details.innerText = `Failed to load modes: ${err}`;
                    label.innerText = 'Error';
                } finally {
                    toggle.disabled = false;
                }
            }

            async function toggleMode(event) {
                const enabled = event.target.checked;
                const nextMode = enabled ? 'ml' : 'rules';
                const toggle = document.getElementById('mode-toggle');
                toggle.disabled = true;
                setPlanStatus(`Switching to ${nextMode === 'ml' ? 'Machine Learning' : 'Rules'} mode…`, { loading: true });
                try {
                    const payload = await window.pywebview.api.set_mode(nextMode);
                    modes = payload.modes || modes;
                    activeMode = payload.active || nextMode;
                    syncModeToggle();
                    setPlanStatus(`Mode updated: ${activeMode === 'ml' ? 'Machine Learning' : 'Rules Engine'}.`, { tone: 'success' });
                    refresh();
                } catch (err) {
                    setPlanStatus(`Failed to switch mode: ${err}`, { tone: 'error' });
                    toggle.checked = !enabled;
                    renderModeDetails(activeMode);
                } finally {
                    toggle.disabled = false;
                }
            }

            async function changeProfile(event) {
                const target = event.target.value;
                const select = document.getElementById('profile-select');
                select.disabled = true;
                document.getElementById('profile-details').innerText = 'Applying profile…';
                try {
                    const payload = await window.pywebview.api.apply_profile(target);
                    profiles = payload.profiles || profiles;
                    activeProfile = payload.active || target;
                    if (activeProfile) {
                        select.value = activeProfile;
                    }
                    renderProfileDetails(activeProfile);
                    setPlanStatus('Model profile updated. New plans will use this configuration.', { tone: 'success' });
                    refresh();
                } catch (err) {
                    setPlanStatus(`Failed to apply profile: ${err}`, { tone: 'error' });
                    if (activeProfile) {
                        select.value = activeProfile;
                        renderProfileDetails(activeProfile);
                    }
                } finally {
                    select.disabled = false;
                }
            }

            async function quitApp() {
                await window.pywebview.api.quit();
            }

            function renderPlanActions(actions) {
                const container = document.getElementById('plan-results');
                container.innerHTML = '';
                if (!actions.length) {
                    container.innerHTML = '<div class="empty-state">Plan returned no actions.</div>';
                    return;
                }
                actions.forEach((item, index) => {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'plan-step';
                    const exec = planExecution[index];
                    const buttonLabel = exec && exec.ok ? 'Re-run' : 'Execute';
                    const statusChip = exec
                        ? `<span class="chip ${exec.ok ? '' : 'error'}">${exec.ok ? (exec.status || 'Dispatched') : 'Failed'}</span>`
                        : '';
                    const detailNotice = exec && exec.detail
                        ? `<div class="plan-step-meta" style="color:#fca5a5;">${exec.detail}</div>`
                        : '';
                    wrapper.innerHTML = `
                        <div class="plan-step-header">
                            <div>
                                <div style="font-weight:600;">Step ${index + 1}: ${item.name}</div>
                                <div class="plan-step-meta">
                                    <span class="chip">${item.preview_required ? 'Preview required' : 'Auto-run'}</span>
                                    <span class="chip">${item.sensitive ? 'Sensitive' : 'Safe'}</span>
                                    ${statusChip}
                                </div>
                                ${detailNotice}
                            </div>
                            <button class="ghost" data-index="${index}">${buttonLabel}</button>
                        </div>
                        <pre style="white-space: pre-wrap;">${item.payload}</pre>
                    `;
                    const btn = wrapper.querySelector('button');
                    if (btn) {
                        btn.addEventListener('click', () => executeAction(index));
                    }
                    container.appendChild(wrapper);
                });
            }

            async function runPlan() {
                const goal = document.getElementById('goal').value.trim();
                if (!goal) {
                    setPlanStatus('Describe a goal first.', { tone: 'error' });
                    return;
                }
                setPlanStatus('Planning actions…', { loading: true });
                try {
                    const payload = await window.pywebview.api.plan(goal);
                    currentPlan = payload.actions || [];
                    planExecution = {};
                    setPlanStatus(`Plan ready with ${currentPlan.length} action${currentPlan.length === 1 ? '' : 's'}.`, { tone: 'success' });
                    renderPlanActions(currentPlan);
                } catch (err) {
                    setPlanStatus(`Planning failed: ${err}`, { tone: 'error' });
                }
            }

            async function runAgent() {
                const goal = document.getElementById('goal').value.trim();
                if (!goal) {
                    setPlanStatus('Describe a goal first.', { tone: 'error' });
                    return;
                }
                setPlanStatus('Running autonomously…', { loading: true });
                try {
                    const payload = await window.pywebview.api.run_agent({ goal });
                    currentPlan = payload && payload.actions ? payload.actions : [];
                    planExecution = {};
                    const results = payload && payload.results ? payload.results : [];
                    for (const result of results) {
                        if (!result || typeof result.index !== 'number') {
                            continue;
                        }
                        const ok = result.ok !== false;
                        const statusLabel = result.status ? result.status : (ok ? 'dispatched' : 'failed');
                        const detail = result.error ? result.error : (result.detail ? result.detail : '');
                        planExecution[result.index] = { ok, status: statusLabel, detail };
                    }
                    const successCount = results.filter((item) => item && item.ok !== false).length;
                    const totalCount = results.length || currentPlan.length;
                    setPlanStatus(`Autonomous run dispatched ${successCount}/${totalCount || successCount} actions.`, { tone: 'success' });
                    renderPlanActions(currentPlan);
                    loadActivity();
                } catch (err) {
                    const message = err && err.message ? err.message : err;
                    setPlanStatus(`Autonomous run failed: ${message}`, { tone: 'error' });
                }
            }

            async function executeAction(index) {
                const action = currentPlan[index];
                if (!action) {
                    return;
                }
                setPlanStatus(`Executing ${action.name}…`, { loading: true });
                try {
                    const response = await window.pywebview.api.execute_action({
                        name: action.name,
                        payload: action.payload,
                        sensitive: action.sensitive,
                        preview_required: action.preview_required,
                    });
                    const resultStatus = response && response.status ? response.status : 'dispatched';
                    const resultDetail = response && response.detail ? response.detail : '';
                    planExecution[index] = { ok: true, status: resultStatus, detail: resultDetail };
                    setPlanStatus(`Action dispatched: ${action.name}.`, { tone: 'success' });
                    loadActivity();
                } catch (err) {
                    const message = err && err.message ? err.message : err;
                    planExecution[index] = { ok: false, status: 'failed', detail: String(message) };
                    setPlanStatus(`Action failed: ${message}`, { tone: 'error' });
                } finally {
                    renderPlanActions(currentPlan);
                }
            }

            async function indexSnippet() {
                const field = document.getElementById('quick-index-text');
                const text = field.value.trim();
                const status = document.getElementById('knowledge-status');
                if (!text) {
                    status.innerText = 'Add text first to index.';
                    return;
                }
                status.innerText = 'Indexing snippet…';
                try {
                    await window.pywebview.api.index_snippet(text);
                    status.innerText = 'Snippet stored successfully.';
                    field.value = '';
                    loadDocuments();
                } catch (err) {
                    status.innerText = `Failed to index: ${err}`;
                }
            }

            function renderDocuments(payload) {
                const table = document.getElementById('knowledge-table');
                const empty = document.getElementById('knowledge-empty');
                const countLabel = document.getElementById('knowledge-count');
                if (!table || !empty) {
                    return;
                }
                const docs = payload && Array.isArray(payload.documents) ? payload.documents : [];
                const total = typeof (payload && payload.count) === 'number' ? payload.count : docs.length;
                table.innerHTML = '';
                setKnowledgeDetailStatus('');
                if (countLabel) {
                    const unit = total === 1 ? 'document' : 'documents';
                    countLabel.innerText = `${total} ${unit} indexed`;
                }
                if (!docs.length) {
                    empty.style.display = 'block';
                    activeDocumentId = null;
                    renderDocumentDetail(null);
                    setKnowledgeDetailStatus('');
                    return;
                }
                empty.style.display = 'none';
                let selectionStillValid = false;
                docs.forEach((doc) => {
                    const meta = doc.meta || {};
                    const row = document.createElement('div');
                    row.className = 'knowledge-row';
                    row.dataset.docId = doc.id;
                    if (doc.id === activeDocumentId) {
                        row.classList.add('active');
                        selectionStillValid = true;
                    }
                    const title = document.createElement('h4');
                    title.textContent = meta.source || 'Unknown source';
                    const metaLine = document.createElement('div');
                    metaLine.className = 'meta';
                    const metaBits = [];
                    if (meta.created_at) {
                        metaBits.push(formatIso(meta.created_at));
                    }
                    if (typeof meta.tokens === 'number') {
                        metaBits.push(`${meta.tokens} tokens`);
                    }
                    metaLine.textContent = metaBits.length ? metaBits.join(' • ') : '—';
                    const preview = document.createElement('div');
                    preview.className = 'preview';
                    preview.textContent = meta.preview || '';
                    row.appendChild(title);
                    row.appendChild(metaLine);
                    row.appendChild(preview);
                    row.addEventListener('click', () => selectDocument(doc.id));
                    table.appendChild(row);
                });
                if (activeDocumentId && !selectionStillValid) {
                    activeDocumentId = null;
                    renderDocumentDetail(null);
                }
                if (!activeDocumentId && docs.length) {
                    selectDocument(docs[0].id, { silent: false });
                } else if (activeDocumentId) {
                    highlightDocumentRow(activeDocumentId);
                }
            }

            function highlightDocumentRow(docId) {
                const rows = document.querySelectorAll('.knowledge-row');
                rows.forEach((row) => {
                    row.classList.toggle('active', row.dataset.docId === docId);
                });
            }

            function setKnowledgeDetailStatus(message) {
                const status = document.getElementById('knowledge-detail-status');
                if (status) {
                    status.innerText = message || '';
                }
            }

            function renderDocumentDetail(doc) {
                const detail = document.getElementById('knowledge-detail');
                if (!detail) {
                    return;
                }
                currentDocumentDetail = doc;
                detail.innerHTML = '';
                if (!doc) {
                    const placeholder = document.createElement('div');
                    placeholder.className = 'empty-state';
                    placeholder.textContent = 'Select a document to inspect its full content.';
                    detail.appendChild(placeholder);
                    return;
                }
                const meta = doc.meta || {};
                const header = document.createElement('div');
                header.style.display = 'flex';
                header.style.justifyContent = 'space-between';
                header.style.gap = '12px';
                const titleWrap = document.createElement('div');
                const title = document.createElement('div');
                title.style.fontWeight = '600';
                title.style.fontSize = '16px';
                title.textContent = meta.source || 'Document';
                const metaLine = document.createElement('div');
                metaLine.style.opacity = '0.65';
                metaLine.style.fontSize = '12px';
                const parts = [];
                if (meta.created_at) {
                    parts.push(formatIso(meta.created_at));
                }
                if (typeof meta.tokens === 'number') {
                    parts.push(`${meta.tokens} tokens`);
                }
                metaLine.textContent = parts.length ? parts.join(' • ') : '—';
                titleWrap.appendChild(title);
                titleWrap.appendChild(metaLine);
                header.appendChild(titleWrap);
                if (doc.id) {
                    const chip = document.createElement('span');
                    chip.className = 'chip';
                    chip.textContent = doc.id.slice(0, 8);
                    header.appendChild(chip);
                }
                detail.appendChild(header);
                if (meta.preview) {
                    const preview = document.createElement('div');
                    preview.style.fontSize = '13px';
                    preview.style.opacity = '0.75';
                    preview.style.lineHeight = '1.6';
                    preview.textContent = meta.preview;
                    detail.appendChild(preview);
                }
                const pre = document.createElement('pre');
                pre.textContent = doc.text || '';
                detail.appendChild(pre);
            }

            async function selectDocument(docId, options = {}) {
                if (!docId) {
                    return;
                }
                const { silent = false } = options;
                activeDocumentId = docId;
                highlightDocumentRow(docId);
                if (silent) {
                    return;
                }
                setKnowledgeDetailStatus('Loading document…');
                try {
                    const doc = await window.pywebview.api.document_detail(docId);
                    renderDocumentDetail(doc);
                    setKnowledgeDetailStatus('');
                } catch (err) {
                    renderDocumentDetail(null);
                    setKnowledgeDetailStatus(`Failed to load: ${err}`);
                }
            }

            async function deleteSelectedDocument() {
                if (!activeDocumentId) {
                    setKnowledgeDetailStatus('Select a document to delete.');
                    return;
                }
                setKnowledgeDetailStatus('Deleting document…');
                try {
                    const payload = await window.pywebview.api.delete_document(activeDocumentId);
                    setKnowledgeDetailStatus('Document removed.');
                    activeDocumentId = null;
                    currentDocumentDetail = null;
                    renderDocumentDetail(null);
                    renderDocuments(payload);
                    refresh();
                    loadDashboard();
                } catch (err) {
                    setKnowledgeDetailStatus(`Failed to delete: ${err}`);
                }
            }

            async function clearKnowledge() {
                setKnowledgeDetailStatus('Clearing knowledge base…');
                try {
                    const payload = await window.pywebview.api.clear_documents();
                    setKnowledgeDetailStatus('Knowledge base cleared.');
                    activeDocumentId = null;
                    currentDocumentDetail = null;
                    renderDocumentDetail(null);
                    renderDocuments(payload);
                    refresh();
                    loadDashboard();
                } catch (err) {
                    setKnowledgeDetailStatus(`Failed to clear: ${err}`);
                }
            }

            async function copyDocumentContent() {
                if (!currentDocumentDetail || !currentDocumentDetail.text) {
                    setKnowledgeDetailStatus('Nothing to copy.');
                    return;
                }
                try {
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        await navigator.clipboard.writeText(currentDocumentDetail.text);
                    } else {
                        const textarea = document.createElement('textarea');
                        textarea.value = currentDocumentDetail.text;
                        textarea.setAttribute('readonly', '');
                        textarea.style.position = 'absolute';
                        textarea.style.left = '-9999px';
                        document.body.appendChild(textarea);
                        textarea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textarea);
                    }
                    setKnowledgeDetailStatus('Copied to clipboard.');
                } catch (err) {
                    setKnowledgeDetailStatus(`Copy failed: ${err}`);
                }
            }

            async function loadDocuments() {
                try {
                    const payload = await window.pywebview.api.documents(40);
                    renderDocuments(payload);
                } catch (err) {
                    const table = document.getElementById('knowledge-table');
                    const empty = document.getElementById('knowledge-empty');
                    if (table) {
                        table.innerHTML = '';
                        const warning = document.createElement('div');
                        warning.className = 'empty-state';
                        warning.textContent = `Failed to load documents: ${err}`;
                        table.appendChild(warning);
                    }
                    if (empty) {
                        empty.style.display = 'block';
                    }
                    setKnowledgeDetailStatus(`Lookup failed: ${err}`);
                }
            }

            function renderQueryHits(hits) {
                const container = document.getElementById('query-results');
                container.innerHTML = '';
                if (!hits.length) {
                    container.innerHTML = '<div class="empty-state">No matches.</div>';
                    return;
                }
                hits.forEach((hit, index) => {
                    const item = document.createElement('div');
                    item.className = 'plan-step';
                    item.innerHTML = `
                        <div class="plan-step-header">
                            <div>
                                <div style="font-weight:600;">Result ${index + 1}</div>
                                <div class="plan-step-meta">Score ${(hit.score || 0).toFixed(3)}</div>
                            </div>
                        </div>
                        <div style="margin-bottom:8px; opacity:0.8;">${hit.text || ''}</div>
                        <pre style="white-space: pre-wrap;">${JSON.stringify(hit, null, 2)}</pre>
                    `;
                    container.appendChild(item);
                });
            }

            async function runQuery() {
                const query = document.getElementById('query-input').value.trim();
                const status = document.getElementById('query-status');
                if (!query) {
                    status.innerText = 'Enter a query to search the vector store.';
                    return;
                }
                status.innerText = 'Searching…';
                try {
                    const payload = await window.pywebview.api.query_index({ query });
                    status.innerText = `Found ${payload.hits.length} results.`;
                    renderQueryHits(payload.hits || []);
                } catch (err) {
                    status.innerText = `Query failed: ${err}`;
                }
            }

            function renderActivity(payload) {
                const feed = document.getElementById('activity-feed');
                const status = document.getElementById('activity-status');
                feed.innerHTML = '';
                if (!payload.events || !payload.events.length) {
                    status.style.display = 'block';
                    status.innerText = 'Listening for new events…';
                    return;
                }
                status.style.display = 'none';
                payload.events.forEach((evt) => {
                    const item = document.createElement('div');
                    item.className = 'activity-item';
                    item.innerHTML = `
                        <div class="activity-type">${evt.type}</div>
                        <div class="activity-meta">${formatIso(evt.ts)}</div>
                        <pre style="white-space: pre-wrap;">${JSON.stringify(evt.payload, null, 2)}</pre>
                    `;
                    feed.appendChild(item);
                });
            }

            function renderLogs(payload) {
                const feed = document.getElementById('logs-feed');
                const count = document.getElementById('logs-count');
                if (!feed) {
                    return;
                }
                const events = payload && Array.isArray(payload.events) ? payload.events : [];
                const total = typeof (payload && payload.count) === 'number' ? payload.count : events.length;
                if (count) {
                    count.innerText = total ? `${total} recorded` : 'No entries';
                }
                if (!events.length) {
                    feed.innerHTML = '<div class="empty-state">No logs yet.</div>';
                    return;
                }
                feed.innerHTML = events.map((evt) => {
                    const type = (evt && evt.type ? String(evt.type) : 'event');
                    const normalized = type.toLowerCase();
                    const severity = normalized.includes('error')
                        ? 'error'
                        : (normalized.includes('success') || normalized.includes('complete') ? 'success' : '');
                    const payloadJson = JSON.stringify(evt.payload, null, 2);
                    return `
                        <div class="log-entry ${severity}">
                            <div class="log-header">
                                <span>${type}</span>
                                <time>${formatIso(evt.ts)}</time>
                            </div>
                            <pre style="margin-top:8px; white-space: pre-wrap;">${payloadJson}</pre>
                        </div>
                    `;
                }).join('');
            }

            async function loadActivity() {
                try {
                    const payload = await window.pywebview.api.activity(40);
                    renderActivity(payload);
                } catch (err) {
                    const status = document.getElementById('activity-status');
                    status.style.display = 'block';
                    status.innerText = `Failed to load activity: ${err}`;
                }
            }

            async function loadLogs(limit = 60) {
                try {
                    const payload = await window.pywebview.api.logs(limit);
                    renderLogs(payload);
                } catch (err) {
                    const feed = document.getElementById('logs-feed');
                    if (feed) {
                        feed.innerHTML = `<div class="empty-state">Failed to load logs: ${err}</div>`;
                    }
                    const count = document.getElementById('logs-count');
                    if (count) {
                        count.innerText = 'Error loading logs';
                    }
                }
            }

            function formatBytes(bytes) {
                if (!bytes || Number.isNaN(bytes)) {
                    return '—';
                }
                const units = ['B', 'KB', 'MB', 'GB', 'TB'];
                let value = bytes;
                let unitIndex = 0;
                while (value >= 1024 && unitIndex < units.length - 1) {
                    value /= 1024;
                    unitIndex += 1;
                }
                return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
            }

            function formatDuration(seconds) {
                if (!seconds || Number.isNaN(seconds)) {
                    return '—';
                }
                const hrs = Math.floor(seconds / 3600);
                const mins = Math.floor((seconds % 3600) / 60);
                const parts = [];
                if (hrs) parts.push(`${hrs}h`);
                parts.push(`${mins}m`);
                return parts.join(' ');
            }

            function normalizeLimitValue(value) {
                if (value === null || value === undefined) {
                    return null;
                }
                const num = Number(value);
                if (!Number.isFinite(num)) {
                    return Infinity;
                }
                if (num < 0) {
                    return Infinity;
                }
                const ABS_INFINITY_THRESHOLD = 1e15;
                if (num > ABS_INFINITY_THRESHOLD) {
                    return Infinity;
                }
                return num;
            }

            function formatLimitValue(value, formatter) {
                const normalized = normalizeLimitValue(value);
                if (normalized === null) {
                    return '—';
                }
                if (!Number.isFinite(normalized)) {
                    return '∞';
                }
                return formatter(normalized);
            }

            function formatLimitPair(limit, formatter) {
                if (!limit || typeof limit !== 'object') {
                    return '—';
                }
                const soft = formatLimitValue(limit.soft, formatter);
                const hard = formatLimitValue(limit.hard, formatter);
                if (soft === hard) {
                    return soft;
                }
                return `${soft} / ${hard}`;
            }

            function formatNumeric(value) {
                if (value === null || value === undefined) {
                    return '—';
                }
                return Number(value).toLocaleString();
            }

            function renderMetrics(metrics) {
                const grid = document.getElementById('metrics-grid');
                const meta = document.getElementById('metrics-meta');
                if (!grid || !meta) {
                    return;
                }
                if (!metrics) {
                    grid.innerHTML = '<div class="empty-state">Metrics unavailable.</div>';
                    meta.innerHTML = '';
                    return;
                }
                const cards = [];
                if (typeof metrics.cpu_percent === 'number') {
                    const percent = Math.min(100, Math.max(0, metrics.cpu_percent));
                    cards.push(`
                        <div class="metric-card">
                            <h3>CPU</h3>
                            <div class="metric-value-large">${percent.toFixed(0)}%</div>
                            <div class="progress"><div class="progress-bar" style="width:${percent}%;"></div></div>
                        </div>
                    `);
                }
                if (typeof metrics.memory_percent === 'number') {
                    const percent = Math.min(100, Math.max(0, metrics.memory_percent));
                    cards.push(`
                        <div class="metric-card">
                            <h3>Memory</h3>
                            <div class="metric-value-large">${percent.toFixed(0)}%</div>
                            <div style="opacity:0.7; font-size:12px;">${formatBytes(metrics.memory_available)} free of ${formatBytes(metrics.memory_total)}</div>
                            <div class="progress"><div class="progress-bar" style="width:${percent}%;"></div></div>
                        </div>
                    `);
                }
                if (typeof metrics.disk_percent === 'number') {
                    const percent = Math.min(100, Math.max(0, metrics.disk_percent));
                    cards.push(`
                        <div class="metric-card">
                            <h3>Disk</h3>
                            <div class="metric-value-large">${percent.toFixed(0)}%</div>
                            <div style="opacity:0.7; font-size:12px;">${formatBytes(metrics.disk_free)} free of ${formatBytes(metrics.disk_total)}</div>
                            <div class="progress"><div class="progress-bar" style="width:${percent}%;"></div></div>
                        </div>
                    `);
                }
                const gpuInfo = metrics.gpu || null;
                if (gpuInfo && typeof gpuInfo.utilization === 'number') {
                    const percent = Math.min(100, Math.max(0, gpuInfo.utilization));
                    cards.push(`
                        <div class="metric-card">
                            <h3>GPU</h3>
                            <div class="metric-value-large">${percent.toFixed(0)}%</div>
                            <div style="opacity:0.7; font-size:12px;">${gpuInfo.name || 'Active device'} • ${formatBytes(gpuInfo.memory_used)} used of ${formatBytes(gpuInfo.memory_total)}</div>
                            <div class="progress"><div class="progress-bar" style="width:${percent}%;"></div></div>
                        </div>
                    `);
                } else {
                    cards.push(`
                        <div class="metric-card">
                            <h3>GPU</h3>
                            <div class="metric-value-large">${gpuInfo && gpuInfo.name ? gpuInfo.name : '—'}</div>
                            <div style="opacity:0.7; font-size:12px;">${gpuInfo ? 'Telemetry unavailable' : 'No GPU detected'}</div>
                        </div>
                    `);
                }
                cards.push(`
                    <div class="metric-card">
                        <h3>Documents</h3>
                        <div class="metric-value-large">${metrics.documents || 0}</div>
                        <div style="opacity:0.7; font-size:12px;">Indexed knowledge entries</div>
                    </div>
                `);
                cards.push(`
                    <div class="metric-card">
                        <h3>Uptime</h3>
                        <div class="metric-value-large">${formatDuration(metrics.uptime_seconds)}</div>
                        <div style="opacity:0.7; font-size:12px;">Since launcher start</div>
                    </div>
                `);
                if (metrics.runtime_pool) {
                    const pool = metrics.runtime_pool;
                    const desired = typeof pool.desired === 'number' ? pool.desired : '—';
                    const active = typeof pool.active === 'number' ? pool.active : '—';
                    cards.push(`
                        <div class="metric-card">
                            <h3>Runtime Pool</h3>
                            <div class="metric-value-large">${active}/${desired}</div>
                            <div style="opacity:0.7; font-size:12px;">Active workers vs desired capacity</div>
                        </div>
                    `);
                }
                if (metrics.sandbox) {
                    const sandbox = metrics.sandbox;
                    const permissions = sandbox.permissions || {};
                    const enabledPerms = Object.values(permissions).filter(Boolean).length;
                    cards.push(`
                        <div class="metric-card">
                            <h3>Sandbox</h3>
                            <div class="metric-value-large">${enabledPerms ? enabledPerms + ' perms' : 'Locked Down'}</div>
                            <div style="opacity:0.7; font-size:12px;">${sandbox.working_dir || '—'}</div>
                        </div>
                    `);
                }
                grid.innerHTML = cards.join('');

                const metaItems = [];
                if (metrics.hostname) {
                    metaItems.push(`<div><strong>Host</strong><br>${metrics.hostname}</div>`);
                }
                if (metrics.platform) {
                    metaItems.push(`<div><strong>Platform</strong><br>${metrics.platform}</div>`);
                }
                metaItems.push(`<div><strong>Events Logged</strong><br>${dashboardState.event_count || 0}</div>`);
                meta.innerHTML = metaItems.join('');
            }

            function renderRuntimePool(pool) {
                const container = document.getElementById('runtime-pool-grid');
                if (!container) {
                    return;
                }
                if (!pool || !Array.isArray(pool.workers) || pool.workers.length === 0) {
                    container.innerHTML = '<div class="empty-state">Runtime pool inactive.</div>';
                    return;
                }
                const summary = `
                    <div class="runtime-summary">
                        <div><strong>Desired</strong><br>${typeof pool.desired === 'number' ? pool.desired : '—'}</div>
                        <div><strong>Active</strong><br>${typeof pool.active === 'number' ? pool.active : '—'}</div>
                        <div><strong>Capacity</strong><br>${pool.capacity ? `${pool.capacity.min} – ${pool.capacity.max}` : '—'}</div>
                    </div>
                `;
                const workers = pool.workers.map((worker) => {
                    const alive = worker.alive !== false;
                    const statusClass = alive ? 'chip' : 'chip error';
                    const statusLabel = alive ? 'Ready' : 'Stopped';
                    const uptime = typeof worker.uptime === 'number' ? formatDuration(worker.uptime) : '—';
                    const cpu = typeof worker.cpu_percent === 'number' ? `${Math.round(worker.cpu_percent)}%` : '—';
                    const mem = typeof worker.memory_rss === 'number' ? formatBytes(worker.memory_rss) : '—';
                    return `
                        <div class="runtime-worker">
                            <div class="runtime-worker-header">
                                <div>
                                    <div class="runtime-worker-name">${worker.name || 'worker'}</div>
                                    <div class="runtime-worker-meta">PID ${worker.pid ?? '—'} • Port ${worker.port ?? '—'}</div>
                                </div>
                                <span class="${statusClass}">${statusLabel}</span>
                            </div>
                            <div class="runtime-worker-stats">
                                <div><strong>Uptime</strong><br>${uptime}</div>
                                <div><strong>Restarts</strong><br>${worker.restarts ?? 0}</div>
                                <div><strong>CPU</strong><br>${cpu}</div>
                                <div><strong>Memory</strong><br>${mem}</div>
                            </div>
                        </div>
                    `;
                }).join('');
                container.innerHTML = summary + workers;
            }

            function renderSandbox(sandbox) {
                const container = document.getElementById('sandbox-grid');
                if (!container) {
                    return;
                }
                if (!sandbox) {
                    container.innerHTML = '<div class="empty-state">Sandbox telemetry unavailable.</div>';
                    return;
                }
                const perms = sandbox.permissions || {};
                const chips = Object.entries(perms).map(([key, value]) => {
                    const label = key.replace(/_/g, ' ');
                    return `<span class="chip ${value ? '' : 'muted'}">${label}</span>`;
                }).join('');
                container.innerHTML = `
                    <div class="sandbox-meta">
                        <div><strong>Working Directory</strong><br>${sandbox.working_dir || '—'}</div>
                    </div>
                    <div class="sandbox-perms">
                        <div class="section-subtitle">Permissions</div>
                        <div class="chips">${chips || '<span class="chip muted">none</span>'}</div>
                    </div>
                `;
            }

            function renderDashboardEvents(events) {
                const wrapper = document.getElementById('dashboard-events');
                if (!wrapper) {
                    return;
                }
                if (!events || !events.length) {
                    wrapper.innerHTML = '<div class="empty-state">No recent events yet.</div>';
                    return;
                }
                wrapper.innerHTML = events.slice(0, 4).map((evt) => `
                    <div class="dashboard-event">
                        <div style="font-weight:600;">${evt.type || 'event'}</div>
                        <div style="opacity:0.6;">${formatIso(evt.ts)}</div>
                        <pre style="margin-top:6px; white-space: pre-wrap;">${JSON.stringify(evt.payload, null, 2)}</pre>
                    </div>
                `).join('');
            }

            function renderQuickGoals(goals) {
                quickGoals = goals || [];
                const list = document.getElementById('quick-goal-list');
                if (!list) {
                    return;
                }
                if (!quickGoals.length) {
                    list.innerHTML = '<div class="empty-state">No automations yet. Create one below!</div>';
                    activeQuickGoal = null;
                    document.getElementById('quick-goal-detail').innerHTML = '<div class="empty-state">Create your first automation to get started.</div>';
                    return;
                }

                if (!activeQuickGoal || !quickGoals.some((item) => item.id === activeQuickGoal.id)) {
                    activeQuickGoal = quickGoals[0];
                }

                list.innerHTML = quickGoals.map((goal) => `
                    <div class="quick-item ${goal.id === (activeQuickGoal && activeQuickGoal.id) ? 'active' : ''}" data-goal-id="${goal.id}">
                        <h4>${goal.label || goal.id}</h4>
                        <p>${goal.description || 'No description provided.'}</p>
                    </div>
                `).join('');

                list.querySelectorAll('.quick-item').forEach((item) => {
                    item.addEventListener('click', () => {
                        const goalId = item.getAttribute('data-goal-id');
                        selectQuickGoal(goalId);
                    });
                });

                selectQuickGoal(activeQuickGoal && activeQuickGoal.id);
            }

            function selectQuickGoal(goalId) {
                if (!goalId) {
                    return;
                }
                const goal = quickGoals.find((item) => item.id === goalId);
                if (!goal) {
                    return;
                }
                activeQuickGoal = goal;
                renderQuickGoalDetail(goal);
                const list = document.getElementById('quick-goal-list');
                if (list) {
                    list.querySelectorAll('.quick-item').forEach((node) => {
                        node.classList.toggle('active', node.getAttribute('data-goal-id') === goalId);
                    });
                }
            }

            function renderQuickGoalDetail(goal) {
                const detail = document.getElementById('quick-goal-detail');
                if (!detail) {
                    return;
                }
                if (!goal) {
                    detail.innerHTML = '<div class="empty-state">Select an automation to view details.</div>';
                    return;
                }
                const fields = (goal.fields || []).filter((field) => field && field.key);
                const fieldsMarkup = fields.length
                    ? `<div class="quick-fields">${fields.map((field) => {
                        const key = field.key;
                        const label = field.label || key;
                        const placeholder = field.placeholder || '';
                        if (field.multiline) {
                            return `
                                <label style="display:flex; flex-direction:column; gap:6px;">
                                    <span style="font-size:12px; opacity:0.7; text-transform:uppercase; letter-spacing:0.08em;">${label}</span>
                                    <textarea data-field-key="${key}" placeholder="${placeholder}"></textarea>
                                </label>
                            `;
                        }
                        return `
                            <label style="display:flex; flex-direction:column; gap:6px;">
                                <span style="font-size:12px; opacity:0.7; text-transform:uppercase; letter-spacing:0.08em;">${label}</span>
                                <input type="text" data-field-key="${key}" placeholder="${placeholder}" />
                            </label>
                        `;
                    }).join('')}</div>`
                    : '<div class="empty-state" style="background: rgba(15,23,42,0.35);">No additional inputs required.</div>';

                detail.innerHTML = `
                    <div>
                        <h3>${goal.label || goal.id}</h3>
                        <div class="plan-step-meta" style="margin-top:6px;">
                            <span class="chip">${goal.category || 'Custom'}</span>
                            <span class="chip">${(goal.mode || 'plan').toUpperCase()}</span>
                        </div>
                        <div style="opacity:0.75; margin-top:8px;">${goal.description || 'No description provided.'}</div>
                    </div>
                    ${fieldsMarkup}
                    <div class="quick-actions">
                        <button class="ghost" data-action="plan">Preview Plan</button>
                        <button class="primary" data-action="auto">Run Autonomously</button>
                        <button class="ghost" data-action="delete">Delete</button>
                    </div>
                    <div id="quick-detail-status" style="font-size:12px; opacity:0.7;"></div>
                `;

                const previewButton = detail.querySelector('[data-action="plan"]');
                const runButton = detail.querySelector('[data-action="auto"]');
                const deleteButton = detail.querySelector('[data-action="delete"]');
                if (previewButton) {
                    previewButton.addEventListener('click', () => runSelectedQuickGoal('plan'));
                }
                if (runButton) {
                    runButton.addEventListener('click', () => runSelectedQuickGoal('auto'));
                }
                if (deleteButton) {
                    deleteButton.addEventListener('click', () => deleteSelectedQuickGoal());
                }
            }

            function collectQuickFieldValues() {
                const detail = document.getElementById('quick-goal-detail');
                if (!detail) {
                    return {};
                }
                const values = {};
                detail.querySelectorAll('[data-field-key]').forEach((input) => {
                    const key = input.getAttribute('data-field-key');
                    if (key) {
                        values[key] = input.value.trim();
                    }
                });
                return values;
            }

            async function runSelectedQuickGoal(mode) {
                if (!activeQuickGoal) {
                    return;
                }
                const detailStatus = document.getElementById('quick-detail-status');
                if (detailStatus) {
                    detailStatus.innerText = mode === 'auto' ? 'Running autonomously…' : 'Generating plan…';
                }
                setPlanStatus(mode === 'auto' ? 'Running quick automation autonomously…' : 'Planning quick automation…', { loading: true });
                const values = collectQuickFieldValues();
                const payload = { id: activeQuickGoal.id, values, mode };
                try {
                    const response = await window.pywebview.api.run_quick_goal(payload);
                    currentPlan = response.actions || [];
                    planExecution = {};
                    if (response.results) {
                        response.results.forEach((result) => {
                            if (result && typeof result.index === 'number') {
                                const ok = result.ok !== false;
                                planExecution[result.index] = {
                                    ok,
                                    status: result.status || (ok ? 'dispatched' : 'failed'),
                                    detail: result.error || result.detail || '',
                                };
                            }
                        });
                    }
                    renderPlanActions(currentPlan);
                    const summary = response.mode === 'auto'
                        ? `Autonomous run dispatched ${(response.results || []).filter((item) => item && item.ok !== false).length}/${(response.results || []).length || currentPlan.length} actions.`
                        : `Generated ${currentPlan.length} actions from automation template.`;
                    setPlanStatus(summary, { tone: 'success' });
                    if (detailStatus) {
                        detailStatus.innerText = summary;
                    }
                    loadActivity();
                    loadDashboard();
                } catch (err) {
                    const message = err && err.message ? err.message : err;
                    setPlanStatus(`Quick automation failed: ${message}`, { tone: 'error' });
                    if (detailStatus) {
                        detailStatus.innerText = `Error: ${message}`;
                    }
                }
            }

            async function deleteSelectedQuickGoal() {
                if (!activeQuickGoal) {
                    return;
                }
                if (!confirm('Delete this automation?')) {
                    return;
                }
                try {
                    const payload = await window.pywebview.api.delete_quick_goal(activeQuickGoal.id);
                    renderQuickGoals(payload.quick_goals || []);
                    const status = document.getElementById('quick-detail-status');
                    if (status) {
                        status.innerText = 'Automation deleted.';
                    }
                    loadDashboard();
                } catch (err) {
                    const status = document.getElementById('quick-detail-status');
                    if (status) {
                        status.innerText = `Failed to delete: ${err}`;
                    }
                }
            }

            async function createQuickGoal() {
                const label = document.getElementById('new-quick-label').value.trim();
                const category = document.getElementById('new-quick-category').value.trim();
                const mode = document.getElementById('new-quick-mode').value;
                const description = document.getElementById('new-quick-description').value.trim();
                const goal = document.getElementById('new-quick-goal').value.trim();
                const fieldsRaw = document.getElementById('new-quick-fields').value.trim();
                const status = document.getElementById('quick-form-status');
                if (!goal) {
                    status.innerText = 'Provide a goal description first.';
                    return;
                }
                const fields = fieldsRaw
                    ? fieldsRaw.split(',').map((name) => name.trim()).filter(Boolean).map((key) => ({
                        key,
                        label: key.replace(/_/g, ' ').replace(/\\b\\w/g, (c) => c.toUpperCase()),
                    }))
                    : [];
                const payload = {
                    label: label || 'Custom Automation',
                    category: category || 'Custom',
                    mode: mode || 'plan',
                    description,
                    goal,
                    fields,
                };
                status.innerText = 'Saving…';
                try {
                    const response = await window.pywebview.api.save_quick_goal(payload);
                    renderQuickGoals(response.quick_goals || []);
                    status.innerText = 'Automation saved.';
                    document.getElementById('new-quick-label').value = '';
                    document.getElementById('new-quick-category').value = '';
                    document.getElementById('new-quick-description').value = '';
                    document.getElementById('new-quick-goal').value = '';
                    document.getElementById('new-quick-fields').value = '';
                    loadDashboard();
                } catch (err) {
                    status.innerText = `Failed to save: ${err}`;
                }
            }

            function renderPermissions(perms) {
                permissionsState = perms || {};
                const list = document.getElementById('permissions-list');
                if (!list) {
                    return;
                }
                const status = document.getElementById('permissions-status');
                if (!perms) {
                    list.innerHTML = '<div class="empty-state">Permissions unavailable.</div>';
                    if (status) status.innerText = '';
                    return;
                }
                const descriptors = [
                    {
                        key: 'file_access',
                        label: 'File Access',
                        description: 'Allow the agent to read and write local files when required.',
                    },
                    {
                        key: 'network_access',
                        label: 'Network Access',
                        description: 'Permit sandboxed actions to reach the network when necessary.',
                    },
                    {
                        key: 'calendar_access',
                        label: 'Calendar Access',
                        description: 'Permit calendar lookups and scheduling automations.',
                    },
                    {
                        key: 'mail_access',
                        label: 'Mail Access',
                        description: 'Enable drafting or sending email on your behalf.',
                    },
                ];
                list.innerHTML = descriptors.map((item) => {
                    const enabled = perms[item.key] ? 'checked' : '';
                    return `
                        <div class="permissions-item">
                            <div>
                                <div style="font-weight:600;">${item.label}</div>
                                <div style="opacity:0.65; font-size:12px;">${item.description}</div>
                            </div>
                            <label class="switch">
                                <input type="checkbox" data-permission="${item.key}" ${enabled} />
                                <span class="slider"></span>
                            </label>
                        </div>
                    `;
                }).join('');
                list.querySelectorAll('input[data-permission]').forEach((input) => {
                    input.addEventListener('change', (event) => {
                        const key = event.target.getAttribute('data-permission');
                        const value = event.target.checked;
                        updatePermission(key, value);
                    });
                });
                if (status) {
                    status.innerText = '';
                }
            }

            async function updatePermission(key, value) {
                if (!key) {
                    return;
                }
                const status = document.getElementById('permissions-status');
                if (status) {
                    status.innerText = 'Updating permission…';
                }
                try {
                    const response = await window.pywebview.api.update_permissions({ [key]: value });
                    renderPermissions(response.permissions || {});
                    if (status) {
                        status.innerText = 'Permission updated.';
                    }
                } catch (err) {
                    if (status) {
                        status.innerText = `Failed to update: ${err}`;
                    }
                }
            }

            async function loadDashboard() {
                try {
                    const payload = await window.pywebview.api.dashboard();
                    dashboardState = payload || {};
                    const metrics = payload.metrics || {};
                    renderMetrics(metrics);
                    renderDashboardEvents(payload.events || []);
                    renderQuickGoals(payload.quick_goals || []);
                    renderPermissions(payload.permissions || {});
                    runtimePoolState = payload.runtime_pool || metrics.runtime_pool || runtimePoolState;
                    sandboxState = metrics.sandbox || payload.sandbox || sandboxState;
                    renderRuntimePool(runtimePoolState);
                    renderSandbox(sandboxState);
                    renderGateway(payload.gateway, payload.gateway_token);
                } catch (err) {
                    const grid = document.getElementById('metrics-grid');
                    if (grid) {
                        grid.innerHTML = `<div class="empty-state">Failed to load dashboard: ${err}</div>`;
                    }
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                initTabs();
                setPlanStatus('No plan generated yet.');
                refresh();
                loadDashboard();
                loadProfiles();
                loadModes();
                loadDocuments();
                loadActivity();
                loadLogs();
                setInterval(refresh, 2000);
                setInterval(loadDashboard, 4000);
                setInterval(loadActivity, 3500);
                setInterval(loadDocuments, 8000);
                setInterval(() => loadLogs(60), 7000);
            });
        </script>
    </body>
    </html>
    """
)


class _Bridge:
    def __init__(self, handle: DaemonHandle) -> None:
        self._handle = handle
        self._window: Optional[Any]
        self._window = None
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[rpc.AssistantStub] = None
        try:
            self._store: Optional[VectorStore] = VectorStore()
        except Exception:
            self._store = None
        self._started_at = time.time()
        self._hostname = platform.node()

    def _document_count(self) -> int:
        store = self._store
        if store is None:
            return 0
        try:
            return int(store.count_docs())
        except Exception:
            return 0

    def _ensure_stub(self) -> rpc.AssistantStub:
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._handle.grpc_address)
            self._stub = rpc.AssistantStub(self._channel)
        return self._stub

    @staticmethod
    def _normalize_timestamp(ts: Any) -> Optional[str]:
        if isinstance(ts, (int, float)):
            try:
                stamp = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                return stamp.isoformat().replace("+00:00", "Z")
            except Exception:
                return None
        if isinstance(ts, str):
            return ts
        return None

    @staticmethod
    def _render_goal(template: str, values: dict[str, str]) -> str:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
        return rendered

    def _recent_events(self, limit: int = 10) -> tuple[list[dict[str, Any]], int]:
        raw_events = list(read_events())
        total = len(raw_events)
        if limit > 0:
            raw_events = raw_events[-limit:]
        # Newest first for the UI
        normalized: list[dict[str, Any]] = []
        for item in reversed(raw_events):
            normalized.append(
                {
                    "type": str(item.get("type", "event")),
                    "ts": self._normalize_timestamp(item.get("ts")),
                    "payload": item,
                }
            )
        return normalized, total

    def _permissions(self) -> dict[str, bool]:
        config = get_config()
        perms = config.get("permissions", {})
        safe: dict[str, bool] = {
            "file_access": bool(perms.get("file_access", False)),
            "network_access": bool(perms.get("network_access", False)),
            "calendar_access": bool(perms.get("calendar_access", False)),
            "mail_access": bool(perms.get("mail_access", False)),
        }
        return safe

    def _update_permissions(self, updates: dict[str, Any]) -> dict[str, bool]:
        config = get_config()
        perms = config.setdefault("permissions", {})
        for key, value in updates.items():
            if key in {"file_access", "network_access", "calendar_access", "mail_access"}:
                perms[key] = bool(value)
        save_config(config)
        sandbox_perms = SandboxPermissions(
            file_access=bool(perms.get("file_access", False)),
            network_access=bool(perms.get("network_access", False)),
            calendar_access=bool(perms.get("calendar_access", False)),
            mail_access=bool(perms.get("mail_access", False)),
        )
        try:
            self._handle.sandbox.update_permissions(sandbox_perms)
        except Exception:
            pass
        return self._permissions()

    def _system_metrics(self) -> dict[str, Any]:
        metrics = self._handle.system_metrics()
        metrics.setdefault("hostname", self._hostname)
        metrics.setdefault("platform", platform.platform())
        return metrics

    def bind(self, window: webview.Window) -> None:
        self._window = window

    def status(self) -> dict[str, Any]:
        config = get_config()
        model_cfg = config.get("model", {})
        active_profile = str(model_cfg.get("profile", ""))
        backend = str(model_cfg.get("backend", "unknown"))
        label = next(
            (profile.get("label", profile.get("id")) for profile in list_model_profiles(config) if profile.get("id") == active_profile),
            active_profile,
        )
        metrics = self._system_metrics()
        gateway_snapshot = self._handle.gateway.snapshot()
        pool_snapshot = metrics.get("runtime_pool") if isinstance(metrics, dict) else None
        documents = int(metrics.get("documents", 0) or 0)
        events, total_events = self._recent_events(limit=1)
        last_event = events[0] if events else None
        return {
            "status": "Daemon running" if self._handle.is_running else "Daemon stopped",
            "runtime": self._handle.runtime_url,
            "grpc": self._handle.grpc_address,
            "backend": backend,
            "profile": active_profile,
            "profile_label": label,
            "mode": str(model_cfg.get("mode", "ml")),
            "documents": documents,
            "event_count": total_events,
            "last_event": last_event,
            "uptime": metrics.get("uptime_seconds"),
            "cpu_percent": metrics.get("cpu_percent"),
            "memory_percent": metrics.get("memory_percent"),
            "gateway": gateway_snapshot["endpoints"],
            "issued_tokens": len(gateway_snapshot["tokens"]),
            "gateway_token": self._handle.auth_token,
            "runtime_pool": pool_snapshot,
            "sandbox": metrics.get("sandbox"),
        }

    def quit(self) -> bool:
        self._handle.stop()
        if self._window is not None:
            self._window.destroy()
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
        return True

    def model_profiles(self) -> dict[str, Any]:
        config = get_config()
        profiles = list_model_profiles(config)
        active_profile = str(config.get("model", {}).get("profile", ""))
        backend = str(config.get("model", {}).get("backend", "unknown"))

        serialized: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            capabilities = profile.get("capabilities")
            serialized.append(
                {
                    "id": str(profile.get("id", "")),
                    "label": str(profile.get("label", profile.get("id", ""))),
                    "description": str(profile.get("description", "")),
                    "backend": str(profile.get("backend", "")),
                    "capabilities": [str(cap) for cap in capabilities] if isinstance(capabilities, list) else [],
                }
            )

        return {
            "active": active_profile,
            "backend": backend,
            "profiles": serialized,
        }

    def model_modes(self) -> dict[str, Any]:
        config = get_config()
        modes = list_model_modes(config)
        active_mode = str(config.get("model", {}).get("mode", "ml"))

        serialized: list[dict[str, Any]] = []
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            capabilities = mode.get("capabilities")
            serialized.append(
                {
                    "id": str(mode.get("id", "")),
                    "label": str(mode.get("label", mode.get("id", ""))),
                    "description": str(mode.get("description", "")),
                    "capabilities": [str(cap) for cap in capabilities] if isinstance(capabilities, list) else [],
                }
            )

        return {"active": active_mode, "modes": serialized}

    def apply_profile(self, profile_id: str) -> dict[str, Any]:
        try:
            apply_model_profile(profile_id)
        except KeyError as exc:  # pragma: no cover - surfaced to UI
            raise RuntimeError(f"Unknown model profile: {profile_id}") from exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError(f"Failed to apply profile: {exc}") from exc
        return self.model_profiles()

    def set_mode(self, mode_id: str) -> dict[str, Any]:
        try:
            set_model_mode(mode_id)
        except KeyError as exc:  # pragma: no cover - surfaced to UI
            raise RuntimeError(f"Unknown mode: {mode_id}") from exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError(f"Failed to update mode: {exc}") from exc
        return self.model_modes()

    def dashboard(self) -> dict[str, Any]:
        metrics = self._system_metrics()
        events, total_events = self._recent_events(limit=8)
        gateway = self._handle.gateway.snapshot()
        return {
            "metrics": metrics,
            "events": events,
            "event_count": total_events,
            "quick_goals": list_quick_goals(),
            "permissions": self._permissions(),
            "gateway": gateway,
            "gateway_token": self._handle.auth_token,
            "runtime_pool": metrics.get("runtime_pool"),
            "sandbox": metrics.get("sandbox"),
        }

    def quick_goals(self) -> dict[str, Any]:
        return {"quick_goals": list_quick_goals()}

    def save_quick_goal(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeError("Goal payload must be an object")
        config = save_quick_goal(payload)
        return {"quick_goals": list_quick_goals(config)}

    def delete_quick_goal(self, goal_id: str) -> dict[str, Any]:
        config = delete_quick_goal(goal_id)
        return {"quick_goals": list_quick_goals(config)}

    def permissions(self) -> dict[str, Any]:
        return {"permissions": self._permissions()}

    def update_permissions(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeError("Permissions payload must be an object")
        perms = self._update_permissions(payload)
        return {"permissions": perms}

    def documents(self, limit: int = 12) -> dict[str, Any]:
        store = self._store
        if store is None:
            return {"documents": [], "count": 0}
        try:
            limit_value = max(1, min(int(limit), 200))
        except Exception:
            limit_value = 12
        try:
            docs = store.list_docs(limit=limit_value)
            total = store.count_docs()
        except Exception as exc:
            raise RuntimeError(f"Failed to load documents: {exc}") from exc
        return {"documents": docs, "count": total, "limit": limit_value}

    def document_detail(self, doc_id: str) -> dict[str, Any]:
        if not doc_id:
            raise RuntimeError("Document id required")
        store = self._store
        if store is None:
            raise RuntimeError("Vector store unavailable")
        try:
            doc = store.get_doc_meta(doc_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to load document: {exc}") from exc
        if not doc:
            raise RuntimeError("Document not found")
        return doc

    def delete_document(self, doc_id: str) -> dict[str, Any]:
        if not doc_id:
            raise RuntimeError("Document id required")
        store = self._store
        if store is None:
            raise RuntimeError("Vector store unavailable")
        try:
            removed = store.delete_doc(doc_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete document: {exc}") from exc
        if not removed:
            raise RuntimeError("Document not found")
        return self.documents()

    def clear_documents(self) -> dict[str, Any]:
        store = self._store
        if store is None:
            return {"documents": [], "count": 0}
        try:
            store.clear()
        except Exception as exc:
            raise RuntimeError(f"Failed to clear documents: {exc}") from exc
        return self.documents()

    def activity(self, limit: int = 40) -> dict[str, Any]:
        try:
            limit_value = max(1, min(int(limit), 200))
        except Exception:
            limit_value = 40
        events, total = self._recent_events(limit=limit_value)
        return {"events": events, "count": total}

    def logs(self, limit: int = 50) -> dict[str, Any]:
        try:
            limit_value = max(1, min(int(limit), 500))
        except Exception:
            limit_value = 50
        events, total = self._recent_events(limit=limit_value)
        return {"events": events, "count": total}

    def index_snippet(self, text: str) -> dict[str, Any]:
        snippet = (text or "").strip()
        if not snippet:
            raise RuntimeError("Snippet must not be empty")
        stub = self._ensure_stub()
        request = PB.IndexRequest(
            id=f"index-{uuid.uuid4()}",
            user_id="desktop",
            text=snippet,
            source="desktop",
            ts=int(time.time()),
        )
        try:
            response = stub.IndexText(request)  # type: ignore[operator]
        except grpc.RpcError as exc:
            detail = exc.details() or exc.code().name
            raise RuntimeError(f"gRPC error: {detail}") from exc
        return {"doc_id": response.doc_id}

    def query_index(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            query = str(payload.get("query", ""))
            k = payload.get("k", 5)
        else:
            query = str(payload)
            k = 5
        query = query.strip()
        if not query:
            raise RuntimeError("Query must not be empty")
        try:
            k_value = max(1, min(int(k), 25))
        except Exception:
            k_value = 5
        stub = self._ensure_stub()
        request = PB.QueryRequest(
            id=f"query-{uuid.uuid4()}",
            user_id="desktop",
            query=query,
            k=k_value,
        )
        try:
            response = stub.Query(request)  # type: ignore[operator]
        except grpc.RpcError as exc:
            detail = exc.details() or exc.code().name
            raise RuntimeError(f"gRPC error: {detail}") from exc
        hits = [
            {
                "doc_id": item.doc_id,
                "score": float(item.score),
                "text": item.text,
            }
            for item in response.hits
        ]
        return {"hits": hits}

    def execute_action(self, action: Any) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise RuntimeError("Action payload must be an object")
        name = str(action.get("name", "")).strip()
        if not name:
            raise RuntimeError("Action name required")
        payload = action.get("payload", "")
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, ensure_ascii=False)
        elif isinstance(payload, str):
            payload_str = payload
        else:
            payload_str = json.dumps(payload, default=str, ensure_ascii=False)
        sensitive = bool(action.get("sensitive", False))
        preview_required = bool(action.get("preview_required", False))

        stub = self._ensure_stub()
        request = PB.Action(
            name=name,
            payload=payload_str,
            sensitive=sensitive,
            preview_required=preview_required,
        )
        try:
            response = stub.ExecuteAction(request)  # type: ignore[operator]
        except grpc.RpcError as exc:
            detail = exc.details() or exc.code().name
            raise RuntimeError(f"gRPC error: {detail}") from exc
        remote_status = 0
        doc_id = ""
        try:
            remote_status = int(getattr(response, "status", 0))
            doc_id = str(getattr(response, "doc_id", ""))
        except Exception:
            remote_status = 0
        payload: dict[str, Any] = {
            "status": "dispatched",
            "remote_status": remote_status,
        }
        if doc_id:
            payload["doc_id"] = doc_id
        if remote_status not in (0,):
            payload["detail"] = f"Runtime status {remote_status}"
        return payload

    def run_quick_goal(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            goal_id = str(payload.get("id") or payload.get("goal_id") or "").strip()
            values_raw = payload.get("values") or {}
            mode_override = payload.get("mode")
        else:
            goal_id = str(payload).strip()
            values_raw = {}
            mode_override = None
        if not goal_id:
            raise RuntimeError("Quick goal id required")

        goals = list_quick_goals()
        goal = next((item for item in goals if item.get("id") == goal_id), None)
        if not goal:
            raise RuntimeError(f"Unknown quick goal: {goal_id}")

        values: dict[str, str] = {}
        if isinstance(values_raw, dict):
            for key, value in values_raw.items():
                if value is None:
                    continue
                values[str(key)] = str(value)

        fields = goal.get("fields", []) if isinstance(goal.get("fields"), list) else []
        for field in fields:
            if not isinstance(field, dict):
                continue
            key = str(field.get("key")) if field.get("key") is not None else ""
            if not key:
                continue
            if key not in values:
                raise RuntimeError(f"Missing value for '{key}'")

        goal_text = self._render_goal(str(goal.get("goal", "")), values).strip()
        if not goal_text:
            raise RuntimeError("Quick goal has no content")

        mode = str(mode_override or goal.get("mode") or "plan").lower()
        result: dict[str, Any]
        if mode in {"auto", "autonomous", "run"}:
            result = self.run_agent({"goal": goal_text})
            result["mode"] = "auto"
        else:
            plan = self.plan(goal_text)
            result = {"mode": "plan", "goal": goal_text, **plan}
        result.setdefault("goal", goal_text)
        result.setdefault("quick_goal", goal_id)
        return result

    def run_agent(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            goal = str(payload.get("goal", ""))
        else:
            goal = str(payload)
        goal = goal.strip()
        if not goal:
            raise RuntimeError("Goal must not be empty")

        plan_result = self.plan(goal)
        actions_raw = plan_result.get("actions", []) if isinstance(plan_result, dict) else []
        normalized_actions: list[dict[str, Any]] = []
        for item in actions_raw:
            if isinstance(item, dict):
                normalized_actions.append(dict(item))
            else:
                normalized_actions.append(
                    {
                        "name": str(item),
                        "payload": json.dumps({"note": str(item)}, ensure_ascii=False),
                        "sensitive": False,
                        "preview_required": False,
                    }
                )

        results: list[dict[str, Any]] = []
        for index, action in enumerate(normalized_actions):
            try:
                execute_result = self.execute_action(action)
            except Exception as exc:
                results.append(
                    {
                        "index": index,
                        "name": str(action.get("name", "")),
                        "status": "failed",
                        "ok": False,
                        "error": str(exc),
                    }
                )
            else:
                results.append(
                    {
                        "index": index,
                        "name": str(action.get("name", "")),
                        "status": str(execute_result.get("status", "")),
                        "ok": True,
                        "detail": str(execute_result.get("detail", "")) if execute_result.get("detail") else "",
                        "remote_status": execute_result.get("remote_status"),
                        "doc_id": execute_result.get("doc_id"),
                    }
                )

        return {"actions": normalized_actions, "results": results}

    def plan(self, goal: str) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise RuntimeError("Goal must not be empty")

        stub = self._ensure_stub()

        request = PB.PlanRequest(
            id=f"launcher-{uuid.uuid4()}",
            user_id="desktop",
            goal=goal,
        )

        try:
            response = stub.Plan(request)  # type: ignore[operator]
        except grpc.RpcError as exc:
            detail = exc.details() or exc.code().name
            raise RuntimeError(f"gRPC error: {detail}") from exc

        actions = [
            {
                "name": item.name,
                "payload": item.payload or "{}",
                "sensitive": item.sensitive,
                "preview_required": item.preview_required,
            }
            for item in response.actions
        ]

        if not actions:
            actions.append({
                "name": "noop",
                "payload": json.dumps({"note": "Assistant returned no plan."}, indent=2),
                "sensitive": False,
                "preview_required": False,
            })

        return {"actions": actions}


def main() -> int:
    try:
        handle = start_daemon()
    except Exception as exc:  # pragma: no cover - surfaced to stderr for Finder launches
        print(f"Failed to start automation daemon: {exc}", file=sys.stderr)
        return 1

    atexit.register(handle.stop)

    api = _Bridge(handle)
    window = webview.create_window(
        "OnDeviceAI",
        html=HTML_TEMPLATE,
        width=760,
        height=640,
        resizable=True,
        min_size=(640, 540),
        js_api=api,
    )
    assert window is not None
    api.bind(window)

    try:
        webview.start(http_server=False, gui="cocoa")
    finally:
        handle.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())

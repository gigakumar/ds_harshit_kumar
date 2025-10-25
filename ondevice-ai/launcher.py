#!/usr/bin/env python
"""Graphical launcher that embeds the automation daemon inside a WebKit window."""
from __future__ import annotations

import atexit
import json
import sys
import textwrap
import uuid
from typing import Any, Optional, cast

import webview

import grpc

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc
from core.config import (
    apply_model_profile,
    get_config,
    list_model_modes,
    list_model_profiles,
    set_model_mode,
)

from automation_daemon import DaemonHandle, start_daemon


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
                background: linear-gradient(145deg, #0f172a, #2563eb);
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
            }
            .card {
                background: rgba(15, 23, 42, 0.9);
                backdrop-filter: blur(22px);
                border-radius: 22px;
                padding: 28px 32px;
                width: 620px;
                box-shadow: 0 24px 60px rgba(15, 23, 42, 0.5);
                color: #f8fafc;
            }
            h1 {
                margin: 0;
                font-size: 28px;
                letter-spacing: -0.01em;
            }
            p.subtitle {
                margin: 6px 0 18px;
                opacity: 0.72;
                font-size: 15px;
            }
            .status {
                background: rgba(37, 99, 235, 0.22);
                border-radius: 12px;
                padding: 14px;
                margin-bottom: 18px;
                font-size: 15px;
                line-height: 1.5;
            }
            .endpoint {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-bottom: 16px;
                font-size: 14px;
            }
            .endpoint span.label {
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 12px;
                opacity: 0.6;
            }
            .endpoint code {
                font-family: "SFMono-Regular", ui-monospace, SFMono-Regular, Menlo, monospace;
                padding: 6px 8px;
                background: rgba(15, 23, 42, 0.6);
                border-radius: 8px;
                color: #cbd5f5;
                word-break: break-all;
            }
            .section {
                margin-top: 18px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .section .label-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
            }
            .section .label {
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 12px;
                opacity: 0.6;
            }
            .section select,
            .section textarea,
            .section input {
                appearance: none;
                border: none;
                border-radius: 12px;
                padding: 12px 14px;
                font-size: 14px;
                background: rgba(15, 23, 42, 0.65);
                color: #e2e8f0;
                font-family: "SFMono-Regular", ui-monospace, Menlo, monospace;
                box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
            }
            .toggle {
                display: flex;
                align-items: center;
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
                background: linear-gradient(135deg, #3b82f6, #2563eb);
            }
            input:checked + .slider:before {
                transform: translateX(22px);
                background: white;
            }
            .section select:focus,
            .section textarea:focus,
            .section input:focus {
                outline: none;
                box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.45);
            }
            .section textarea {
                resize: vertical;
                min-height: 110px;
            }
            .section .helper {
                font-size: 13px;
                opacity: 0.7;
                line-height: 1.5;
                background: rgba(15, 23, 42, 0.55);
                border-radius: 14px;
                padding: 14px;
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
                padding: 6px 10px;
                border-radius: 999px;
                background: rgba(59, 130, 246, 0.25);
                color: #bfdbfe;
            }
            .actions {
                display: flex;
                gap: 12px;
                justify-content: flex-end;
                flex-wrap: wrap;
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
                background: linear-gradient(135deg, #3b82f6, #2563eb);
                color: white;
                box-shadow: 0 12px 24px rgba(37, 99, 235, 0.35);
            }
            button.secondary {
                background: rgba(15, 23, 42, 0.7);
                color: #cbd5f5;
            }
            button:hover {
                transform: translateY(-1px);
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>OnDeviceAI</h1>
            <p class="subtitle">Local-first automation daemon with an embedded control panel.</p>
            <div id="status" class="status">Preparing backend…</div>
            <div class="endpoint">
                <span class="label">Runtime URL</span>
                <code id="runtime"></code>
            </div>
            <div class="endpoint">
                <span class="label">gRPC Endpoint</span>
                <code id="grpc"></code>
            </div>

            <div class="section" id="model-section">
                <div class="label-row">
                    <span class="label">Model Profile</span>
                    <select id="profile-select" onchange="changeProfile(event)"></select>
                </div>
                <div class="helper" id="profile-details">Loading model profiles…</div>
            </div>

            <div class="section" id="mode-section">
                <div class="label-row">
                    <span class="label">Intelligence Mode</span>
                    <div class="toggle">
                        <label class="switch">
                            <input type="checkbox" id="mode-toggle" onchange="toggleMode(event)" />
                            <span class="slider"></span>
                        </label>
                        <span id="mode-label" style="font-size: 13px; margin-left: 8px; opacity: 0.75;">Checking…</span>
                    </div>
                </div>
                <div class="helper" id="mode-details">Determining available modes…</div>
            </div>

            <div class="section">
                <label class="label" for="goal">Automation Goal</label>
                <textarea id="goal" placeholder="Describe what you want the assistant to do"></textarea>
                <div class="actions">
                    <button class="secondary" onclick="quitApp()">Quit</button>
                    <button class="primary" onclick="runPlan()">Plan Automation</button>
                </div>
            </div>

            <div id="plan-status" class="helper">No plan yet.</div>
            <div id="plan-results" style="margin-top: 12px; background: rgba(15,23,42,0.55); border-radius: 14px; padding: 18px; max-height: 240px; overflow-y: auto; font-size: 13px;"></div>
        </div>

        <script>
            async function refresh() {
                const payload = await window.pywebview.api.status();
                const label = payload.profile_label ? `${payload.status} • ${payload.profile_label}` : payload.status;
                document.getElementById('status').innerText = label;
                document.getElementById('runtime').innerText = payload.runtime;
                document.getElementById('grpc').innerText = payload.grpc;
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
            }

            let profiles = [];
            let activeProfile = null;
            let modes = [];
            let activeMode = null;

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
                    profiles = payload.profiles || [];
                    activeProfile = payload.active || null;
                    select.innerHTML = '';
                    for (const profile of profiles) {
                        const option = document.createElement('option');
                        option.value = profile.id;
                        option.textContent = profile.label || profile.id;
                        select.appendChild(option);
                    }
                    if (activeProfile) {
                        select.value = activeProfile;
                    }
                    renderProfileDetails(select.value);
                } catch (err) {
                    select.innerHTML = '';
                    document.getElementById('profile-details').innerText = `Failed to load model profiles: ${err}`;
                } finally {
                    select.disabled = profiles.length === 0;
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
                const status = document.getElementById('plan-status');
                toggle.disabled = true;
                status.innerText = `Switching to ${nextMode === 'ml' ? 'Machine Learning' : 'Rules'} mode…`;
                try {
                    const payload = await window.pywebview.api.set_mode(nextMode);
                    modes = payload.modes || modes;
                    activeMode = payload.active || nextMode;
                    syncModeToggle();
                    status.innerText = `Mode updated: ${activeMode === 'ml' ? 'Machine Learning' : 'Rules Engine'}.`;
                    refresh();
                } catch (err) {
                    status.innerText = `Failed to switch mode: ${err}`;
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
                    document.getElementById('plan-status').innerText = 'Model profile updated. New plans will use this configuration.';
                    refresh();
                } catch (err) {
                    document.getElementById('plan-status').innerText = `Failed to apply profile: ${err}`;
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

            async function runPlan() {
                const goal = document.getElementById('goal').value.trim();
                if (!goal) {
                    document.getElementById('plan-status').innerText = 'Describe a goal first.';
                    return;
                }
                document.getElementById('plan-status').innerText = 'Planning…';
                try {
                    const payload = await window.pywebview.api.plan(goal);
                    document.getElementById('plan-status').innerText = `Received ${payload.actions.length} actions.`;
                    document.getElementById('plan-results').innerHTML = payload.actions.map((item, index) => `
                        <div style="margin-bottom: 10px;">
                            <div style="font-weight: 600;">Step ${index + 1}: ${item.name}</div>
                            <pre style="margin: 4px 0 0; white-space: pre-wrap; background: rgba(15,23,42,0.45); padding: 8px; border-radius: 10px;">${item.payload}</pre>
                        </div>
                    `).join('');
                } catch (err) {
                    document.getElementById('plan-status').innerText = `Planning failed: ${err}`;
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                refresh();
                setInterval(refresh, 1500);
                loadProfiles();
                loadModes();
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
        return {
            "status": "Daemon running" if self._handle.is_running else "Daemon stopped",
            "runtime": self._handle.runtime_url,
            "grpc": self._handle.grpc_address,
            "backend": backend,
            "profile": active_profile,
            "profile_label": label,
            "mode": str(model_cfg.get("mode", "ml")),
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

    def plan(self, goal: str) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise RuntimeError("Goal must not be empty")

        if self._stub is None:
            self._channel = grpc.insecure_channel(self._handle.grpc_address)
            self._stub = rpc.AssistantStub(self._channel)
        assert self._stub is not None

        pb = cast(Any, pb_module)
        request = pb.PlanRequest(
            id=f"launcher-{uuid.uuid4()}",
            user_id="desktop",
            goal=goal,
        )

        try:
            response = self._stub.Plan(request)  # type: ignore[operator]
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

// SPDX-License-Identifier: MIT

pragma Singleton

import QtQuick

QtObject {
    id: state

    // One controller per greeter engine, shared by every display. Secrets live
    // only in memory and each PAM prompt receives at most one response.
    property var backend: null
    property string password: ""
    property string queuedPassword: ""
    property bool queued: false
    property bool submitting: false
    property bool promptReady: false
    property double retryNotBefore: 0
    property string message: ""
    readonly property bool retrying: retryTimer.running || queued

    signal authenticated()

    function initialize(authenticator) {
        if (!backend) {
            backend = authenticator;
            backend.startAuthenticating();
        }
    }

    function clear() {
        password = "";
        queuedPassword = "";
        if (queued) {
            submitting = false;
        }
        queued = false;
    }

    function submit() {
        if (!backend || submitting || password.length === 0) {
            return;
        }
        queuedPassword = password;
        queued = true;
        submitting = true;
        submitQueued();
    }

    function submitQueued() {
        if (!queued || !promptReady || retryTimer.running) {
            return;
        }
        const response = queuedPassword;
        queuedPassword = "";
        password = "";
        queued = false;
        promptReady = false;
        message = "";
        backend.respond(response);
    }

    property Connections backendConnections: Connections {
        target: state.backend

        function onFailed(kind) {
            if (kind !== 0) {
                return;
            }
            state.clear();
            state.submitting = false;
            state.promptReady = false;
            state.message = "Unlocking failed";
            state.retryTimer.interval = Math.max(3000, state.retryNotBefore - Date.now());
            state.retryTimer.restart();
        }

        function onLoginFailedDelayStarted(kind, authenticator, microseconds) {
            if (kind === 0) {
                state.retryNotBefore = Date.now() + Math.ceil(microseconds / 1000);
                if (state.retryTimer.running) {
                    state.retryTimer.interval = Math.max(3000, state.retryNotBefore - Date.now());
                    state.retryTimer.restart();
                }
            }
        }

        function onPromptForSecretChanged() {
            state.promptReady = true;
            state.submitting = state.queued;
            state.submitQueued();
        }

        function onPromptChanged() {
            state.message = state.backend.prompt;
            state.promptReady = true;
            state.submitting = state.queued;
            state.submitQueued();
        }

        function onInfoMessageChanged() {
            state.message = state.backend.infoMessage;
        }

        function onErrorMessageChanged() {
            state.message = state.backend.errorMessage;
        }

        function onSucceeded() {
            state.retryTimer.stop();
            state.clear();
            state.submitting = false;
            state.promptReady = false;
            state.retryNotBefore = 0;
            state.message = "";
            state.authenticated();
        }
    }

    property Timer retryTimer: Timer {
        onTriggered: {
            state.promptReady = false;
            state.backend.startAuthenticating();
        }
    }
}
